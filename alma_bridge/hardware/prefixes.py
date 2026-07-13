from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional


PREFIXES_ROOT = Path.home() / ".local/share/alma-bridge/prefixes"

KNOWN_APP_MARKERS = {
    "ascension": Path("drive_c/Program Files/Ascension Launcher/Ascension Launcher.exe"),
}


def list_prefixes() -> List[Dict[str, Any]]:
    if not PREFIXES_ROOT.exists():
        return []

    entries: List[Dict[str, Any]] = []
    for prefix in sorted(PREFIXES_ROOT.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not prefix.is_dir():
            continue
        apps = _installed_apps(prefix)
        entries.append(
            {
                "path": str(prefix),
                "name": prefix.name,
                "apps": apps,
            }
        )
    return entries


def find_best_prefix(file_path: str) -> Optional[str]:
    """Reuse an existing Alma Bridge prefix when the target belongs to it."""
    path = Path(file_path).resolve()
    if not PREFIXES_ROOT.exists():
        return None

    for prefix in PREFIXES_ROOT.iterdir():
        if not prefix.is_dir():
            continue
        try:
            path.relative_to(prefix)
            return str(prefix)
        except ValueError:
            continue

    lowered = str(path).lower()
    for keyword, marker in KNOWN_APP_MARKERS.items():
        if keyword not in lowered and keyword not in path.name.lower():
            continue
        for prefix in sorted(PREFIXES_ROOT.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if (prefix / marker).exists():
                return str(prefix)

    return None


def _installed_apps(prefix: Path) -> List[str]:
    apps: List[str] = []
    for keyword, marker in KNOWN_APP_MARKERS.items():
        if (prefix / marker).exists():
            apps.append(keyword)
    return apps
