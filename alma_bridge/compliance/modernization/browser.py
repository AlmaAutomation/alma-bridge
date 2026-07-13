"""Browser detection, recommendation, and low-RAM launch profiles for legacy hosts."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from alma_bridge.compliance.pm import detect_package_manager, install_cmd

# Binaries we recognize, best-first within each tier.
_BROWSER_CANDIDATES = [
    ("firefox", "Firefox"),
    ("firefox-esr", "Firefox ESR"),
    ("librewolf", "LibreWolf"),
    ("chromium", "Chromium"),
    ("chromium-browser", "Chromium"),
    ("google-chrome", "Google Chrome"),
    ("google-chrome-stable", "Google Chrome"),
    ("brave-browser", "Brave"),
    ("epiphany", "GNOME Web"),
    ("midori", "Midori"),
    ("falkon", "Falkon"),
    ("netsurf", "NetSurf"),
    ("dillo", "Dillo"),
]

# Package names per manager for install recommendations.
_BROWSER_PACKAGES: Dict[str, Dict[str, List[str]]] = {
    "apt": {
        "full": ["firefox-esr"],
        "light": ["firefox-esr"],
        "minimal": ["netsurf"],
        "chromium": ["chromium"],
    },
    "dnf": {
        "full": ["firefox"],
        "light": ["firefox"],
        "minimal": ["epiphany"],
        "chromium": ["chromium"],
    },
    "yum": {
        "full": ["firefox"],
        "light": ["firefox"],
        "minimal": ["epiphany"],
        "chromium": ["chromium"],
    },
    "pacman": {
        "full": ["firefox"],
        "light": ["firefox"],
        "minimal": ["dillo"],
        "chromium": ["chromium"],
    },
    "zypper": {
        "full": ["MozillaFirefox"],
        "light": ["MozillaFirefox"],
        "minimal": ["MozillaFirefox"],
        "chromium": ["chromium"],
    },
    "apk": {
        "full": ["firefox-esr"],
        "light": ["firefox-esr"],
        "minimal": ["dillo"],
        "chromium": ["chromium"],
    },
}

# Launch flags / env for constrained hardware (potato mode).
_POTATO_PROFILES: Dict[str, Dict[str, Any]] = {
    "firefox": {
        "env": {
            "MOZ_DISABLE_CONTENT_SANDBOX": "1",
            "MOZ_DISABLE_GMP_SANDBOX": "1",
        },
        "args": [
            "--new-instance",
            "--disable-gpu",
            "--no-remote",
        ],
        "user_js": {
            "browser.cache.disk.enable": False,
            "browser.cache.memory.enable": True,
            "browser.cache.memory.capacity": 32768,
            "layers.acceleration.disabled": True,
            "media.autoplay.default": 5,
            "dom.ipc.processCount": 1,
        },
    },
    "chromium": {
        "env": {},
        "args": [
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disk-cache-size=1",
            "--media-cache-size=1",
            "--disable-background-networking",
            "--disable-extensions",
            "--no-sandbox",
        ],
        "user_js": {},
    },
    "netsurf": {
        "env": {},
        "args": [],
        "user_js": {},
    },
}


def _browser_version(binary: str) -> Optional[str]:
    try:
        proc = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        line = (proc.stdout or proc.stderr or "").strip().splitlines()[0]
        return line[:120] if line else None
    except (OSError, subprocess.SubprocessError, IndexError):
        return None


def assess_browsers() -> Dict[str, Any]:
    """Inventory installed browsers and whether any looks modern enough for HTTPS."""
    installed: List[Dict[str, Any]] = []
    for binary, label in _BROWSER_CANDIDATES:
        path = shutil.which(binary)
        if not path:
            continue
        installed.append(
            {
                "binary": binary,
                "path": path,
                "label": label,
                "version": _browser_version(path),
            }
        )
    modern_ok = any(
        b["binary"] in {"firefox", "firefox-esr", "chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "brave-browser", "librewolf"}
        for b in installed
    )
    return {
        "installed": installed,
        "count": len(installed),
        "has_modern_browser": modern_ok,
        "has_any_browser": len(installed) > 0,
    }


def _ram_tier(ram_mb: Optional[int]) -> str:
    if ram_mb is None:
        return "light"
    if ram_mb < 768:
        return "minimal"
    if ram_mb < 2048:
        return "light"
    return "full"


def recommend_browser(
    *,
    ram_mb: Optional[int] = None,
    os_release: Optional[str] = None,
    prefer_chromium: bool = False,
) -> Dict[str, Any]:
    """Pick a browser + install command + potato launch profile for this host."""
    pm = detect_package_manager(os_release)
    tier = _ram_tier(ram_mb)
    pkgs_map = _BROWSER_PACKAGES.get(pm, _BROWSER_PACKAGES["apt"])
    if prefer_chromium and "chromium" in pkgs_map:
        pkg_key = "chromium"
        binary = "chromium" if pm != "apt" else "chromium-browser"
        engine = "chromium"
    elif tier == "minimal":
        pkg_key = "minimal"
        binary = "netsurf" if pm == "apt" else "dillo"
        engine = "netsurf" if pm == "apt" else "dillo"
    else:
        pkg_key = tier if tier in pkgs_map else "light"
        binary = "firefox-esr" if pm == "apt" else "firefox"
        engine = "firefox"

    packages = pkgs_map.get(pkg_key, pkgs_map["light"])
    install_cmd_str = install_cmd(packages, pm)
    profile_key = "firefox" if "firefox" in binary or engine == "firefox" else engine
    profile = _POTATO_PROFILES.get(profile_key, _POTATO_PROFILES["firefox"])

    launch_script = _build_launch_script(binary, profile, tier)

    return {
        "tier": tier,
        "recommended_binary": binary,
        "recommended_label": next((l for b, l in _BROWSER_CANDIDATES if b == binary), binary),
        "packages": packages,
        "install_command": install_cmd_str,
        "package_manager": pm,
        "potato_mode": tier in {"minimal", "light"},
        "launch_env": profile["env"],
        "launch_args": profile["args"],
        "user_js": profile.get("user_js", {}),
        "launch_script": launch_script,
        "notes": _browser_notes(tier, binary),
    }


def _browser_notes(tier: str, binary: str) -> str:
    if tier == "minimal":
        return (
            f"Very low RAM — {binary} is lightweight but some modern sites need Alma's "
            "TLS bridge + a fuller browser when memory allows."
        )
    if tier == "light":
        return "Low RAM — use the potato launch script (single content process, no GPU, tiny cache)."
    return "Standard profile; potato flags still help on older GPUs and spinning disks."


def _build_launch_script(binary: str, profile: Dict[str, Any], tier: str) -> str:
    env_lines = "\n".join(f'export {k}="{v}"' for k, v in profile["env"].items())
    args = " ".join(profile["args"])
    js_block = ""
    if profile.get("user_js") and "firefox" in binary:
        js_lines = "\n".join(
            f'echo \'user_pref("{k}", {v});\' >> "$PROFILE/user.js"'
            for k, v in profile["user_js"].items()
        )
        js_block = f'''PROFILE="${{HOME}}/.mozilla/firefox/alma-potato.default"
mkdir -p "$PROFILE"
: > "$PROFILE/user.js"
{js_lines}
'''
    env_section = env_lines if env_lines else "# no extra env"
    return f"""#!/bin/bash
# Alma legacy browser launcher — potato-optimized ({tier} tier)
{env_section}
{js_block}exec {binary} {args} "$@"
"""
