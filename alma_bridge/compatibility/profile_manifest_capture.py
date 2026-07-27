from __future__ import annotations

"""Authoritative bridge-manifest capture from verified execution state."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional

from alma_bridge.execution.preflight import read_wine_windows_version
from alma_bridge.schemas.models import AttemptRecord
from alma_bridge.validation.prefix_drift import read_prefix_installed_components

MANIFEST_CAPTURE_VERSION = "manifest_capture_v2"
COMPONENT_CAPTURE_COMPLETE_VERSION = MANIFEST_CAPTURE_VERSION


@dataclass(frozen=True)
class VerifiedManifestContext:
    """Captured prefix/runtime state at verified-success time."""

    winetricks_components: List[str]
    windows_version: Optional[str]
    prefix_architecture: str
    dll_overrides: Dict[str, str]
    wrapper_versions: Dict[str, str]
    config_hashes: Dict[str, str]
    manifest_capture_version: str
    component_capture_complete: bool


def _wine_prefix(record: AttemptRecord) -> Optional[str]:
    env = record.env or {}
    prefix = env.get("WINEPREFIX")
    return str(prefix) if prefix else None


def _detect_prefix_architecture(prefix: str) -> str:
    root = Path(prefix).expanduser()
    if (root / "drive_c/windows/syswow64").is_dir():
        return "win64"
    if (root / "drive_c/windows/system32").is_dir():
        return "win64"
    return "win32"


def _parse_dll_overrides(env: Mapping[str, str]) -> Dict[str, str]:
    raw = str(env.get("WINEDLLOVERRIDES") or "").strip()
    if not raw:
        return {}
    overrides: Dict[str, str] = {}
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry or "=" not in entry:
            continue
        dll, mode = entry.split("=", 1)
        overrides[dll.strip().lower()] = mode.strip().lower()
    return dict(sorted(overrides.items()))


def _irrelevant_marker_files(prefix: str) -> List[str]:
    """Files that must never be inferred as winetricks components."""
    root = Path(prefix).expanduser()
    noise = []
    for pattern in ("*.tmp", "*.log", "dosdevices/*"):
        for path in root.glob(pattern):
            if path.is_file():
                noise.append(str(path.relative_to(root)))
    return noise


def capture_verified_manifest_context(
    *,
    record: AttemptRecord,
    wine_version: Optional[str] = None,
) -> VerifiedManifestContext:
    """Capture authoritative manifest fields from the verified bridge attempt."""
    prefix = _wine_prefix(record)
    env = record.env or {}
    components: List[str] = []
    windows_version: Optional[str] = None
    prefix_architecture = "win64"

    if prefix:
        components = read_prefix_installed_components(prefix)
        try:
            windows_version = read_wine_windows_version(prefix)
        except Exception:  # noqa: BLE001
            windows_version = None
        prefix_architecture = _detect_prefix_architecture(prefix)
        _irrelevant_marker_files(prefix)  # side-effect audit hook for tests

    return VerifiedManifestContext(
        winetricks_components=sorted(components),
        windows_version=windows_version,
        prefix_architecture=prefix_architecture,
        dll_overrides=_parse_dll_overrides(env),
        wrapper_versions={},
        config_hashes={},
        manifest_capture_version=MANIFEST_CAPTURE_VERSION,
        component_capture_complete=True,
    )


def manifest_reconstruction_eligible(manifest: Mapping[str, object]) -> tuple[bool, Optional[str]]:
    """Return whether a stored manifest supports active reconstruction."""
    capture_version = manifest.get("manifest_capture_version")
    if not capture_version:
        return False, "MANIFEST_CAPTURE_VERSION_MISSING"
    if str(capture_version) != COMPONENT_CAPTURE_COMPLETE_VERSION:
        return False, f"MANIFEST_CAPTURE_VERSION_UNSUPPORTED:{capture_version}"
    if not manifest.get("component_capture_complete", False):
        return False, "COMPONENT_CAPTURE_INCOMPLETE"
    return True, None


def normalize_component_list(components: Optional[List[str]]) -> List[str]:
    """Deterministic component ordering for identity hashing."""
    return sorted(str(c) for c in (components or []))


def components_identity_key(components: List[str]) -> str:
    return "|".join(normalize_component_list(components))
