"""Make program binaries runnable before Bridge executes them."""

from __future__ import annotations

import os
import shlex
import stat
from pathlib import Path
from typing import Any, Dict, Optional

from alma_bridge.compliance.modernization.apply import _privileged_shell
from alma_bridge.execution.privileges import prepare_sudo


def _is_executable(path: Path) -> bool:
    """Return True when the file mode and access checks agree it can execute."""
    mode = path.stat().st_mode
    if not (mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)):
        return False
    return os.access(str(path), os.X_OK)


def ensure_binary_executable(
    file_path: str,
    *,
    sudo_password: Optional[str] = None,
) -> Dict[str, Any]:
    """Ensure a native binary/AppImage has execute permission."""
    path = Path(file_path).expanduser()
    if not path.exists():
        return {"ok": False, "changed": False, "path": str(path), "reason": "file not found"}

    if _is_executable(path):
        return {"ok": True, "changed": False, "path": str(path)}

    quoted = shlex.quote(str(path))
    try:
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR)
        if os.access(str(path), os.X_OK):
            return {"ok": True, "changed": True, "path": str(path), "method": "chmod_user"}
    except OSError as user_err:
        last_err = str(user_err)
    else:
        last_err = "chmod did not grant execute permission"

    sudo_ok, sudo_err = prepare_sudo(requested=True, password=sudo_password)
    if not sudo_ok:
        return {
            "ok": False,
            "changed": False,
            "path": str(path),
            "reason": sudo_err or last_err,
        }

    result = _privileged_shell(f"sudo chmod +x {quoted}", sudo_password=sudo_password)
    if result.get("ok") and os.access(str(path), os.X_OK):
        return {
            "ok": True,
            "changed": True,
            "path": str(path),
            "method": "sudo_chmod",
        }

    return {
        "ok": False,
        "changed": False,
        "path": str(path),
        "reason": (result.get("stderr") or last_err or "chmod +x failed").strip(),
    }
