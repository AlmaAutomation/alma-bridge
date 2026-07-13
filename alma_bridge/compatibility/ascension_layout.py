"""Ascension launcher layout canonicalization (flat vs nested Squirrel install)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, List, Optional

ASCENSION_INSTALL_BASE = Path("drive_c/Program Files/Ascension Launcher")
NESTED_DIR_NAME = "Ascension Launcher"


def ascension_launcher_layout(launcher_path: str) -> str:
    """Return ``nested`` or ``flat`` for an Ascension launcher executable path."""
    launcher = Path(launcher_path).expanduser()
    parts = launcher.parts
    try:
        idx = parts.index("Ascension Launcher")
    except ValueError:
        return "flat"
    # nested: .../Ascension Launcher/Ascension Launcher/Ascension Launcher.exe
    if (
        idx + 2 < len(parts)
        and parts[idx + 1] == NESTED_DIR_NAME
        and launcher.name.lower().endswith(".exe")
    ):
        return "nested"
    return "flat"


def ascension_resources_for_launcher(launcher_path: str) -> Path:
    """Resources directory that belongs to the selected launcher install root."""
    launcher = Path(launcher_path).expanduser()
    return launcher.parent / "resources"


def ascension_install_root(launcher_path: str) -> Path:
    """Directory containing the canonical launcher exe and its resources/."""
    return Path(launcher_path).expanduser().parent


def ascension_stale_flat_resources_dir(
    wine_prefix: str,
    canonical_launcher: str,
) -> Optional[Path]:
    """Flat-level resources/ left behind when the canonical launcher is nested."""
    if ascension_launcher_layout(canonical_launcher) != "nested":
        return None
    prefix = Path(wine_prefix).expanduser()
    stale = prefix / ASCENSION_INSTALL_BASE / "resources"
    canonical_resources = ascension_resources_for_launcher(canonical_launcher)
    try:
        if stale.resolve() == canonical_resources.resolve():
            return None
    except OSError:
        if stale == canonical_resources:
            return None
    if stale.is_dir():
        return stale
    return None


def quarantine_stale_ascension_flat_layout(
    wine_prefix: str,
    canonical_launcher: str,
) -> Dict[str, object]:
    """Move stale flat-layout resources aside so Electron cannot invoke the wrong sidecar."""
    stale = ascension_stale_flat_resources_dir(wine_prefix, canonical_launcher)
    if not stale:
        return {"action": "quarantine_stale_flat_resources", "status": "skipped"}

    quarantine_root = stale.parent / ".alma-quarantine-flat-layout"
    quarantine_root.mkdir(parents=True, exist_ok=True)
    dest = quarantine_root / "resources"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(stale), str(dest))
    return {
        "action": "quarantine_stale_flat_resources",
        "status": "quarantined",
        "from": str(stale),
        "to": str(dest),
        "canonical_launcher": canonical_launcher,
        "canonical_resources": str(ascension_resources_for_launcher(canonical_launcher)),
    }


def ascension_path_provenance(
    wine_prefix: str,
    canonical_launcher: str,
) -> List[Dict[str, object]]:
    """Enumerate Ascension-related paths and their layout classification."""
    prefix = Path(wine_prefix).expanduser()
    launcher = Path(canonical_launcher).expanduser()
    resources = ascension_resources_for_launcher(canonical_launcher)
    rows: List[Dict[str, object]] = []

    def add_row(
        role: str,
        path: Path,
        *,
        producer: str,
        consumer: str,
    ) -> None:
        exists = path.exists()
        layout = "nested" if "Ascension Launcher/Ascension Launcher" in str(path) else "flat"
        if role == "stale_flat_resources":
            layout = "flat_stale"
        entry: Dict[str, object] = {
            "role": role,
            "path": str(path),
            "normalized": str(path),
            "realpath": str(path.resolve()) if exists else None,
            "layout": layout,
            "exists": exists,
            "sha256": None,
            "producer": producer,
            "consumer": consumer,
            "in_disposable_prefix": str(path).startswith(str(prefix)),
        }
        if exists and path.is_file():
            import hashlib

            h = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(65536), b""):
                    h.update(chunk)
            entry["sha256"] = h.hexdigest()
            entry["size"] = path.stat().st_size
        rows.append(entry)

    add_row("canonical_launcher", launcher, producer="ascension_main_launcher_path", consumer="BridgeOrchestrator")
    add_row("launcher_cwd", launcher.parent, producer="launch_plan", consumer="wine CreateProcess")
    add_row("canonical_resources", resources, producer="ascension_resources_for_launcher", consumer="prepare_electron_wine")
    stale = ascension_stale_flat_resources_dir(wine_prefix, canonical_launcher)
    if stale:
        add_row("stale_flat_resources", stale, producer="historical_install", consumer="Electron sidecar (stale)")
    for name in ("AscensionClientServices.exe", "AscensionClientServices.real.exe"):
        add_row(
            f"sidecar_{name}",
            resources / name,
            producer="install_cs_guard_wrapper",
            consumer="cs_wrapper / Electron",
        )
    add_row(
        "decoy",
        resources / "alma-guard" / launcher.name,
        producer="install_launcher_decoy",
        consumer="cs_wrapper",
    )
    add_row("invoke_log", prefix / "drive_c/alma-cs-invoke.log", producer="cs_wrapper.c", consumer="electron_handoff")
    add_row("output_log", prefix / "drive_c/alma-cs-output.log", producer="cs_wrapper.c", consumer="electron_handoff")
    return rows
