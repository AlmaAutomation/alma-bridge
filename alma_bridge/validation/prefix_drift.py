from __future__ import annotations

"""Deterministic prefix drift helpers for validation campaigns."""

from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from alma_bridge.execution.preflight import read_wine_windows_version, set_wine_windows_version

# Component markers: package name -> relative paths that must exist when installed.
COMPONENT_MARKERS: dict[str, tuple[str, ...]] = {
    "corefonts": (
        "drive_c/windows/Fonts/arial.ttf",
        "drive_c/windows/Fonts/times.ttf",
    ),
}


def read_prefix_windows_version(wine_prefix: str) -> Optional[str]:
    if not wine_prefix:
        return None
    try:
        return read_wine_windows_version(wine_prefix)
    except Exception:  # noqa: BLE001
        return None


def apply_windows_version_mutation(wine_prefix: str, version: str) -> Tuple[bool, str]:
    return set_wine_windows_version(wine_prefix, version)


def read_prefix_installed_components(wine_prefix: str) -> List[str]:
    """Infer installed validation components from deterministic marker files."""
    if not wine_prefix:
        return []
    root = Path(wine_prefix).expanduser()
    present: List[str] = []
    for package, markers in COMPONENT_MARKERS.items():
        if all((root / marker).is_file() for marker in markers):
            present.append(package)
    return sorted(present)


def remove_component_from_prefix(wine_prefix: str, component: str) -> Tuple[bool, str]:
    """Remove a frozen component from a disposable clone by deleting marker files."""
    markers = COMPONENT_MARKERS.get(component)
    if not markers:
        return False, f"unknown component: {component}"
    root = Path(wine_prefix).expanduser()
    removed = 0
    for marker in markers:
        path = root / marker
        if path.is_file():
            path.unlink()
            removed += 1
    if removed == 0:
        return False, f"component {component} markers not found"
    observed = read_prefix_installed_components(wine_prefix)
    if component in observed:
        return False, f"component {component} still detected after removal"
    return True, f"removed {removed} marker file(s) for {component}"


def verify_component_absent(wine_prefix: str, component: str) -> bool:
    return component not in read_prefix_installed_components(wine_prefix)


def verify_windows_version(wine_prefix: str, expected: str) -> bool:
    return read_prefix_windows_version(wine_prefix) == expected


def baseline_component_set(wine_prefix: str) -> List[str]:
    return read_prefix_installed_components(wine_prefix)
