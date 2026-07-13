from __future__ import annotations

from typing import Any, Dict, Optional

from alma_bridge.compatibility.electron_wine import mingw_compiler
from alma_bridge.execution.program_preflight import check_program_readiness


def check_installer_readiness(
    file_path: str,
    *,
    wine_prefix: Optional[str] = None,
) -> Dict[str, Any]:
    result = check_program_readiness(file_path, wine_prefix=wine_prefix)
    if result.get("is_installer"):
        return result
    warnings = list(result.get("warnings") or [])
    warnings.append("Target does not look like a Windows installer.")
    result["warnings"] = warnings
    return result


def check_launcher_readiness(
    file_path: str,
    *,
    wine_prefix: Optional[str] = None,
) -> Dict[str, Any]:
    result = check_program_readiness(file_path, wine_prefix=wine_prefix)
    if not result.get("is_launcher") and result.get("program_kind") != "pe_electron_launcher":
        warnings = list(result.get("warnings") or [])
        warnings.append(
            "Target does not look like an Electron launcher — Bridge will still try Wine strategies."
        )
        result["warnings"] = warnings
    result["is_installer"] = False
    result["is_ascension"] = "ascension" in file_path.lower()
    if result["is_ascension"] and not mingw_compiler():
        warnings = list(result.get("warnings") or [])
        warnings.append(
            "Ascension needs gcc-mingw-w64-x86-64 to build Electron-on-Wine wrappers "
            "(sidecar guard + elevate passthrough). Install: sudo apt install gcc-mingw-w64-x86-64"
        )
        result["warnings"] = warnings
    return result
