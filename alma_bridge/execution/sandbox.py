from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from alma_bridge.config import settings
from alma_bridge.execution.container_checks import sandbox_ready
from alma_bridge.execution.container_spec import build_container_run_spec
from alma_bridge.execution.privileges import wrap_with_sudo


def run_in_container(
    command: List[str],
    *,
    env: Dict[str, str],
    file_path: str,
    timeout_sec: int,
    use_sudo: bool = False,
    extra_run_args: Optional[List[str]] = None,
    sandbox_image: Optional[str] = None,
) -> Tuple[int, str, str]:
    ready, runtime = sandbox_ready(use_sudo=use_sudo)
    if not ready or not runtime:
        from alma_bridge.config import PROJECT_ROOT

        hint = (
            f"Container sandbox unavailable. Build the image with: "
            f"cd {PROJECT_ROOT} && docker build -t {settings.sandbox_image} ."
        )
        return 127, "", hint

    target = Path(file_path).resolve()
    if not target.exists():
        return 127, "", f"File not found: {target}"

    spec = build_container_run_spec(
        file_path=str(target),
        command=command,
        env=env,
        image=sandbox_image,
        runtime=runtime,
        use_sudo=use_sudo,
        extra_args=extra_run_args,
    )
    run_cmd = spec["argv"]

    try:
        proc = subprocess.run(
            run_cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        if proc.returncode != 0 and not use_sudo and _needs_sudo_retry(proc.stderr):
            return run_in_container(
                command,
                env=env,
                file_path=file_path,
                timeout_sec=timeout_sec,
                use_sudo=True,
                extra_run_args=extra_run_args,
                sandbox_image=sandbox_image,
            )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        return -1, exc.stdout or "", (exc.stderr or "") + "\nExecution timed out in container."
    except OSError as exc:
        return 127, "", str(exc)


def _needs_sudo_retry(stderr: str) -> bool:
    text = (stderr or "").lower()
    return any(
        marker in text
        for marker in (
            "permission denied",
            "got permission denied",
            "cannot connect to the docker daemon",
            "access denied",
        )
    )
