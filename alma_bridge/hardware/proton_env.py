from __future__ import annotations

from pathlib import Path
from typing import Dict


def resolve_steam_root(proton_bin: str) -> str:
    proton = Path(proton_bin).resolve()
    for parent in proton.parents:
        if (parent / "steam.sh").exists():
            return str(parent)
        if parent.name == "Steam" and (parent / "steamapps").exists():
            return str(parent)
    parts = proton.parts
    if "compatibilitytools.d" in parts:
        idx = parts.index("compatibilitytools.d")
        if idx > 0:
            return str(Path(*parts[:idx]))
    default = Path.home() / ".local/share/Steam"
    if default.exists():
        return str(default)
    return str(Path.home() / ".steam" / "root")


def compat_data_path(session_id: str) -> Path:
    path = Path.home() / ".local/share/alma-bridge/proton-compat" / session_id[:12]
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_proton_env(proton_bin: str, session_id: str) -> Dict[str, str]:
    compat = compat_data_path(session_id)
    steam_root = resolve_steam_root(proton_bin)
    return {
        "STEAM_COMPAT_DATA_PATH": str(compat),
        "STEAM_COMPAT_CLIENT_INSTALL_PATH": steam_root,
        "WINEPREFIX": str(compat / "pfx"),
        "WINEDEBUG": "-all",
    }
