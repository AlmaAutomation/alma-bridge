from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache
from typing import Optional, Tuple

from alma_bridge.config import settings
from alma_bridge.execution.privileges import wrap_with_sudo


def container_runtime() -> Optional[str]:
    if shutil.which("docker"):
        return "docker"
    if shutil.which("podman"):
        return "podman"
    return None


@lru_cache(maxsize=4)
def _image_exists(runtime: str, image: str, use_sudo: bool) -> bool:
    command = wrap_with_sudo([runtime, "image", "inspect", image], use_sudo=use_sudo)
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def sandbox_ready(use_sudo: bool = False) -> Tuple[bool, Optional[str]]:
    """Return whether container sandbox can run and which runtime to use."""
    runtime = container_runtime()
    if not runtime or not settings.sandbox_enabled:
        return False, None

    if _image_exists(runtime, settings.sandbox_image, use_sudo=False):
        return True, runtime

    if use_sudo and _image_exists(runtime, settings.sandbox_image, use_sudo=True):
        return True, runtime

    return False, runtime


def clear_sandbox_cache() -> None:
    _image_exists.cache_clear()
