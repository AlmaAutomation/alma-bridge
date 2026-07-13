from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Dict, List, Optional

from alma_bridge.learning.installer import ASCENSION_SKIP_UPDATE_ARGS, electron_software_gl_args


_DISABLED_UPDATE_YML = """provider: generic
url: http://127.0.0.1:1/alma-disabled-update
updaterCacheDirName: projectascension-updater-disabled
"""


def _launcher_resources_dir(launcher_path: str) -> Optional[Path]:
    launcher = Path(launcher_path).expanduser()
    if not launcher.is_file():
        return None
    resources = launcher.parent / "resources"
    if resources.is_dir():
        return resources
    return launcher.parent if launcher.parent.is_dir() else None


def disable_ascension_auto_updater(
    wine_prefix: str,
    launcher_path: str,
) -> Dict[str, Any]:
    """Neuter Electron auto-update so Wine never silently runs ascension-setup."""
    actions: List[Dict[str, Any]] = []
    resources = _launcher_resources_dir(launcher_path)
    if resources:
        update_yml = resources / "app-update.yml"
        backup = resources / "app-update.yml.orig"
        if update_yml.is_file() and not backup.is_file():
            backup.write_text(update_yml.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        if update_yml.is_file():
            update_yml.write_text(_DISABLED_UPDATE_YML, encoding="utf-8")
            actions.append({"kind": "app_update_yml", "path": str(update_yml), "status": "disabled"})

    prefix_root = Path(wine_prefix).expanduser()
    settings_candidates = [
        prefix_root / "drive_c/users/joshua/AppData/Local/ProjectAscension/Config/AscensionLauncherSettings.json",
        prefix_root / "drive_c/users/joshua/AppData/Roaming/ProjectAscension/Config/AscensionLauncherSettings.json",
    ]
    for settings_path in settings_candidates:
        if not settings_path.parent.is_dir():
            continue
        data: Dict[str, Any] = {}
        if settings_path.is_file():
            try:
                data = json.loads(settings_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
        data["disableAutoUpdate"] = True
        data["autoUpdate"] = False
        data["almaBridgeUpdateDisabled"] = True
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        actions.append({"kind": "launcher_settings", "path": str(settings_path), "status": "updated"})

    pending = (
        prefix_root
        / "drive_c/users/joshua/AppData/Local/projectascension-updater/pending"
    )
    if pending.is_dir():
        for setup in pending.glob("ascension-setup-*.exe"):
            try:
                setup.unlink()
                actions.append({"kind": "cleared_pending_update", "path": str(setup)})
            except OSError:
                pass

    return {"ok": True, "actions": actions}


def write_ascension_launch_wrapper(
    wine_prefix: str,
    launcher_path: str,
) -> Optional[str]:
    """Install a host script that launches Ascension with Bridge-safe Wine flags."""
    launcher = Path(launcher_path).expanduser().resolve()
    if not launcher.is_file():
        return None

    bin_dir = Path.home() / ".local/share/alma-bridge/bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    wrapper = bin_dir / "launch-ascension.sh"

    wine = os.environ.get("ALMA_WINE", "wine")
    args = " ".join(electron_software_gl_args() + ASCENSION_SKIP_UPDATE_ARGS)
    script = f"""#!/usr/bin/env bash
set -euo pipefail
export WINEPREFIX="{Path(wine_prefix).expanduser().resolve()}"
export WINEDEBUG="${{WINEDEBUG:--all}}"
export ELECTRON_DISABLE_CRASH_REPORTER=1
export ALMA_SKIP_ELECTRON_UPDATE=1
exec {wine} "{launcher}" {args} "$@"
"""
    wrapper.write_text(script, encoding="utf-8")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(wrapper)
