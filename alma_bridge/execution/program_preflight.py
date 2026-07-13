from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from alma_bridge.compatibility.electron_wine import mingw_compiler
from alma_bridge.compatibility.program_kind import classify_program_kind
from alma_bridge.execution.installer_verify import discover_installed_launcher, launcher_verified_in_prefix
from alma_bridge.execution.preflight import prefix_dotnet_installed, prefix_runtimes_ready
from alma_bridge.hardware.prefixes import find_best_prefix, list_prefixes
from alma_bridge.hardware.profiler import profile_hardware


def _display_ready() -> tuple[bool, Optional[str]]:
    display = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    if display:
        return True, display
    return False, None


def check_program_readiness(
    file_path: str,
    *,
    wine_prefix: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate host readiness for any program Bridge can run."""
    path = Path(file_path).expanduser()
    hardware = profile_hardware()
    host_arch = hardware.get("architecture", "x86_64")
    kind = classify_program_kind(str(path), host_arch=host_arch)

    wine_path = (hardware.get("paths") or {}).get("wine")
    wine_available = bool(wine_path and Path(str(wine_path)).exists()) or bool(
        shutil.which("wine")
    )
    display_ok, display_value = _display_ready()

    suggested_prefix = wine_prefix or find_best_prefix(str(path)) if kind["exists"] else wine_prefix
    prefix_path = Path(suggested_prefix).expanduser() if suggested_prefix else None
    prefix_exists = bool(prefix_path and prefix_path.is_dir())
    prefix_writable = bool(prefix_path and os.access(prefix_path, os.W_OK)) if prefix_exists else False

    blockers: List[str] = []
    warnings: List[str] = []

    if not kind["exists"]:
        blockers.append(f"File not found: {path}")
    elif kind["program_kind"] == "missing":
        blockers.append("Unable to classify program format.")

    if kind["needs_wine"] and not wine_available:
        blockers.append("Wine is not installed or not on PATH.")

    if kind["needs_gui"] and not display_ok:
        blockers.append(
            "No GUI session detected (DISPLAY/WAYLAND_DISPLAY unset). "
            "Windows GUI programs need an active desktop session."
        )

    if kind["needs_native"] and kind["exists"] and not os.access(path, os.X_OK):
        if kind["program_kind"] != "native_script":
            warnings.append("Binary is not marked executable — Bridge may still try to run it.")

    if suggested_prefix and not prefix_exists:
        warnings.append(f"Wine prefix does not exist yet: {suggested_prefix}")
    elif prefix_exists and not prefix_writable:
        blockers.append(f"Wine prefix is not writable: {suggested_prefix}")

    if kind["needs_wine"] and display_ok and not suggested_prefix:
        warnings.append(
            "No existing Wine prefix matched — Bridge will create a fresh prefix for this session."
        )

    installed_launcher_path = None
    if kind["is_installer"] and suggested_prefix:
        installed_launcher_path = discover_installed_launcher(
            suggested_prefix,
            str(path),
        )
        if installed_launcher_path:
            if (
                launcher_verified_in_prefix(suggested_prefix, installed_launcher_path)
                and prefix_runtimes_ready(suggested_prefix)
            ):
                warnings.append(
                    "An installed launcher was found in this Wine prefix — Bridge will skip "
                    f"re-running the installer and launch: {installed_launcher_path}"
                )
            elif launcher_verified_in_prefix(suggested_prefix, installed_launcher_path):
                warnings.append(
                    "Launcher was verified before but .NET/VC++ runtimes are missing in the prefix — "
                    "Bridge will bootstrap runtimes before launch."
                )
            else:
                warnings.append(
                    "A launcher exists in this prefix but never verified successfully — Bridge "
                    f"will re-run the installer first (found: {installed_launcher_path})."
                )
                installed_launcher_path = None

    if kind["needs_wine"] and suggested_prefix and prefix_exists and not prefix_dotnet_installed(
        suggested_prefix
    ):
        warnings.append(
            ".NET Framework is not installed in this Wine prefix yet — Bridge will install it "
            "automatically before launch (a learn.microsoft.com browser tab during install is normal)."
        )

    if "ascension" in str(path).lower() and not mingw_compiler():
        warnings.append(
            "Ascension on Wine needs gcc-mingw-w64-x86-64 for sidecar/elevate wrappers. "
            "Install: sudo apt install gcc-mingw-w64-x86-64 — Bridge will try to install it automatically."
        )

    ready = not blockers
    return {
        **kind,
        "ready": ready,
        "display": display_value,
        "wine_available": wine_available,
        "wine_path": wine_path or shutil.which("wine"),
        "suggested_wine_prefix": suggested_prefix,
        "prefix_exists": prefix_exists,
        "prefix_writable": prefix_writable,
        "known_prefixes": list_prefixes()[:6],
        "blockers": blockers,
        "warnings": warnings,
        "installed_launcher_path": installed_launcher_path,
    }
