"""Docker/Podman run specification — mounts, env, caps, shim-driven flags."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any, Dict, List, Optional

from alma_bridge.config import settings
from alma_bridge.execution.container_checks import container_runtime, sandbox_ready
from alma_bridge.execution.container_command import container_workspace_path
from alma_bridge.execution.privileges import wrap_with_sudo


def _env_args(env: Dict[str, str]) -> List[str]:
    args: List[str] = []
    for key, value in env.items():
        args.extend(["-e", f"{key}={value}"])
    return args


def _shim_container_flags(env: Dict[str, str]) -> List[str]:
    """Translate Alma shim env hints into ``docker run`` flags."""
    flags: List[str] = ["--init", "--cap-drop=ALL", "--security-opt", "no-new-privileges"]

    network = env.get("ALMA_CONTAINER_NETWORK", "bridge")
    flags.extend(["--network", network])

    memory = env.get("ALMA_CONTAINER_MEMORY")
    if memory:
        flags.extend(["--memory", memory])

    cpus = env.get("ALMA_CONTAINER_CPUS")
    if cpus:
        flags.extend(["--cpus", cpus])

    if env.get("LIBGL_ALWAYS_SOFTWARE") == "1":
        flags.extend(["-e", "DISPLAY="])

    return flags


def build_container_run_spec(
    *,
    file_path: str,
    command: List[str],
    env: Dict[str, str],
    image: Optional[str] = None,
    runtime: Optional[str] = None,
    use_sudo: bool = False,
    extra_args: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Return argv list and a human-readable preview for a container run."""
    image = image or settings.sandbox_image
    runtime = runtime or container_runtime() or "docker"

    target = Path(file_path).resolve()
    mount_dir = str(target.parent)
    in_container_path = container_workspace_path(str(target))

    container_cmd = list(command)
    if container_cmd and Path(container_cmd[0]).resolve() == target:
        container_cmd[0] = in_container_path
    elif container_cmd and container_cmd[-1] == str(target):
        container_cmd[-1] = in_container_path
    elif len(container_cmd) == 1 and container_cmd[0] == str(target):
        container_cmd[0] = in_container_path

    run_argv: List[str] = [
        runtime,
        "run",
        "--rm",
        *_shim_container_flags(env),
        "-v",
        f"{mount_dir}:/workspace:ro",
        *_env_args(env),
        *(extra_args or []),
        image,
        *container_cmd,
    ]
    run_argv = wrap_with_sudo(run_argv, use_sudo=use_sudo)

    return {
        "runtime": runtime,
        "image": image,
        "mount": f"{mount_dir}:/workspace:ro",
        "command": container_cmd,
        "env": env,
        "argv": run_argv,
        "preview": shlex.join(run_argv),
    }
