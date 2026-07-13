"""Template-based pathway synthesis for novel / bridge errors."""

from __future__ import annotations

import re
from typing import Any, Dict, List


def build_novel_pathway_extras(
    error_text: str,
    diagnoses: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build extra remediation pathways without re-entering plan_pathways."""
    extras: List[Dict[str, Any]] = []
    text = (error_text or "").lower()
    top_sig = (diagnoses[0].get("signature") if diagnoses else "") or "unknown_error"

    if re.search(r"out of memory|cannot allocate|oom", text):
        extras.append(_pathway(
            "novel_enable_zram",
            "Enable compressed swap (zram) for low-memory hosts",
            [
                "sudo apt-get install -y zram-tools || sudo modprobe zram",
                "sudo systemctl enable --now zramswap 2>/dev/null || true",
            ],
        ))

    if re.search(r"fontconfig|libfontconfig", text):
        extras.append(_pathway(
            "novel_install_fonts",
            "Install fontconfig stack for GUI/browser apps",
            ["sudo apt-get install -y fontconfig libfontconfig1"],
        ))

    if re.search(r"libnss|nss_", text):
        extras.append(_pathway(
            "novel_install_nss",
            "Install NSS libraries for TLS/HTTPS in browsers",
            ["sudo apt-get install -y libnss3"],
        ))

    if "permission_denied" in text or top_sig == "permission_denied":
        extras.append(_pathway(
            "novel_fresh_wineprefix",
            "Create a fresh WINEPREFIX and retry (fixes bad prefix permissions)",
            [
                "rm -rf ~/.wine-alma-fresh && WINEARCH=win64 WINEPREFIX=~/.wine-alma-fresh wineboot -i",
            ],
        ))
        extras.append(_pathway(
            "novel_fix_wine_permissions",
            "Repair ownership on the active Wine prefix",
            [
                "sudo chown -R \"$USER:$USER\" ~/.wine 2>/dev/null || true",
                "chmod -R u+rwx ~/.wine 2>/dev/null || true",
            ],
        ))

    if ".appimage" in text:
        extras.append(_pathway(
            "novel_appimage_extract",
            "Extract AppImage and run payload directly",
            [
                "chmod +x BINARY && BINARY --appimage-extract && ./squashfs-root/AppRun",
            ],
        ))

    if "winetricks" in text or "vcrun" in text or "dotnet" in text:
        extras.append(_pathway(
            "novel_winetricks_core",
            "Install core Windows runtimes via winetricks",
            [
                "winetricks -q vcrun2019 vcrun2022 corefonts 2>/dev/null || true",
            ],
        ))

    for extra in extras:
        extra["synthesized"] = True
        extra["score"] = 0.96

    return extras


def _pathway(pid: str, title: str, commands: List[str]) -> Dict[str, Any]:
    return {
        "id": pid,
        "title": title,
        "signature": "unknown_error",
        "category": "novel",
        "priority": 0,
        "rebuild": True,
        "steps": [
            {
                "description": title,
                "command": cmd,
                "kind": "remediation",
                "requires_root": "sudo" in cmd,
            }
            for cmd in commands
        ],
    }
