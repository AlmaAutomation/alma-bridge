from __future__ import annotations

from typing import Any, Dict, Optional

from alma_bridge.execution.program_preflight import check_program_readiness


def check_installer_readiness(
    file_path: str,
    *,
    wine_prefix: Optional[str] = None,
) -> Dict[str, Any]:
    result = check_program_readiness(file_path, wine_prefix=wine_prefix)
    if not result.get("is_installer"):
        warnings = list(result.get("warnings") or [])
        warnings.append("Target does not look like a Windows installer.")
        result["warnings"] = warnings
    return result
