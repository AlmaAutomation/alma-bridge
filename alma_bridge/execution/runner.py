from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from alma_bridge.config import settings
from alma_bridge.execution.preflight import require_wine_windows_version
from alma_bridge.execution.errors import (
    HARD_FAIL_SIGNATURES,
    classify_execution_error,
    detect_error_signature,
    launch_failure_in_log,
    suggest_fix,
)
from alma_bridge.execution.privileges import resolve_use_sudo, wrap_with_sudo
from alma_bridge.execution.sandbox import run_in_container
from alma_bridge.execution.wine_process import wine_rundll32_active
from alma_bridge.schemas.models import ExecutionMode

WINE_RUNTIMES = {"wine", "proton"}


def file_hash(path: str) -> Optional[str]:
    target = Path(path)
    if not target.exists() or not target.is_file():
        return None
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def execute_attempt(
    *,
    command: List[str],
    env: Dict[str, str],
    file_path: str,
    mode: ExecutionMode,
    timeout_sec: Optional[int] = None,
    extra_args: Optional[List[str]] = None,
    use_sudo: bool = False,
    detach_gui: bool = False,
    detach_after_sec: Optional[int] = None,
) -> Dict[str, object]:
    timeout = timeout_sec or settings.execution_timeout_sec
    detach_after = detach_after_sec or settings.launcher_detach_after_sec
    started = time.perf_counter()
    command = _append_launch_args(command, extra_args or [])

    # Wine/Proton/native runs must never use sudo — only Docker may need it.
    sudo_for_container = (
        mode == ExecutionMode.CONTAINER
        and resolve_use_sudo(use_sudo)
    )

    if mode == ExecutionMode.CONTAINER and settings.sandbox_enabled:
        exit_code, stdout, stderr = run_in_container(
            command,
            env=env,
            file_path=file_path,
            timeout_sec=timeout,
            use_sudo=sudo_for_container,
        )
    else:
        exit_code, stdout, stderr = _run_on_host(
            command,
            env,
            timeout,
            use_sudo=False,
            detach_gui=detach_gui,
            detach_after_sec=detach_after,
        )

    duration_ms = int((time.perf_counter() - started) * 1000)
    signature = detect_error_signature(stderr, stdout)
    hard_fail = signature in HARD_FAIL_SIGNATURES
    success = exit_code == 0 and not hard_fail
    pending_launch_eval = (
        detach_gui
        and "[alma] launcher detached" in str(stderr or "").lower()
    )
    if pending_launch_eval:
        # Process may still be starting — electron_handoff decides real success.
        success = False
        fail_sig = launch_failure_in_log(str(stderr), str(stdout))
        if fail_sig:
            signature = fail_sig
            success = False
    if success:
        detected_error, likely_causes = None, []
    else:
        detected_error, likely_causes = classify_execution_error(stderr, stdout)
        if hard_fail and exit_code == 0:
            likely_causes = list(likely_causes)

    return {
        "success": success,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "detected_error": detected_error,
        "likely_causes": likely_causes,
        "error_signature": signature,
        "suggested_fix": suggest_fix(signature, stderr, stdout),
        "duration_ms": duration_ms,
    }


def _append_launch_args(command: List[str], extra_args: List[str]) -> List[str]:
    if not extra_args or not command:
        return command

    runtime = Path(command[0]).name.lower()
    if runtime in {"wine", "proton", "proton-run"} or command[0] in WINE_RUNTIMES:
        if runtime == "proton" or "proton" in command[0].lower():
            # proton run <exe> [args]
            if len(command) >= 3 and command[1] == "run":
                return command[:3] + extra_args + command[3:]
            return command + extra_args
        return command[:2] + extra_args + command[2:]
    return command + extra_args


def _run_on_host(
    command: List[str],
    env: Dict[str, str],
    timeout_sec: int,
    *,
    use_sudo: bool = False,
    detach_gui: bool = False,
    detach_after_sec: int = 45,
) -> Tuple[int, str, str]:
    merged_env = os.environ.copy()
    merged_env.update(env)
    command = list(command)

    if "DISPLAY" not in merged_env and os.environ.get("DISPLAY"):
        merged_env.setdefault("DISPLAY", os.environ["DISPLAY"])

    if "ALMA_WINE_VIRTUAL_DESKTOP" in merged_env:
        size = merged_env.pop("ALMA_WINE_VIRTUAL_DESKTOP")
        merged_env["WINEDLLOVERRIDES"] = merged_env.get("WINEDLLOVERRIDES", "")
        merged_env["DISPLAY"] = merged_env.get("DISPLAY", ":0")
        runtime = command[0] if command else ""
        if runtime and (Path(runtime).name.lower() in {"wine", "proton", "proton-run"} or "proton" in runtime.lower()):
            target_and_args = command[3:] if len(command) >= 3 and command[1] == "run" else command[1:]
            command = [
                runtime if "proton" not in runtime.lower() else "wine",
                "explorer",
                f"/desktop=AlmaDesktop,{size}",
                *target_and_args,
            ]

    run_cmd = wrap_with_sudo(command, use_sudo=use_sudo)

    # GUI apps under Wine/Proton (especially Electron) must be handed VALID stdio.
    # subprocess capture_output uses pipes + inherits the server's (often closed)
    # stdin; under Wine an Electron main process then dies with
    # "Error: open EBADF ... at new Socket ... createWritableStdioStream" because
    # Node builds a net.Socket over the pipe fd. Redirecting to a real file makes
    # Node use a plain file stream instead, which works.
    if _is_wine_runtime(command):
        prefix = merged_env.get("WINEPREFIX")
        if prefix:
            require_wine_windows_version(prefix)
        if detach_gui:
            return _run_gui_detach(
                run_cmd,
                merged_env,
                bootstrap_sec=detach_after_sec,
                max_wait_sec=timeout_sec,
            )
        return _run_gui_to_file(run_cmd, merged_env, timeout_sec)

    try:
        proc = subprocess.run(
            run_cmd,
            capture_output=True,
            text=True,
            env=merged_env,
            timeout=timeout_sec,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        return -1, exc.stdout or "", (exc.stderr or "") + "\nExecution timed out."
    except OSError as exc:
        return 127, "", str(exc)


def _is_wine_runtime(command: List[str]) -> bool:
    if not command:
        return False
    head = command[0]
    name = Path(head).name.lower()
    return name in {"wine", "wine64", "proton", "proton-run"} or "proton" in head.lower()


def _gui_log_path(merged_env: Dict[str, str]) -> str:
    prefix = merged_env.get("WINEPREFIX")
    base = Path(prefix) if prefix and Path(prefix).is_dir() else Path(tempfile.gettempdir())
    return str(base / f"alma-run-{os.getpid()}-{int(time.time() * 1000)}.log")


def _run_gui_to_file(
    run_cmd: List[str],
    merged_env: Dict[str, str],
    timeout_sec: int,
) -> Tuple[int, str, str]:
    """Run a Wine/Proton GUI app with a valid NUL stdin and a real log file for
    stdout/stderr, then read the log back. Avoids the Wine pipe-fd EBADF crash."""
    log_path = _gui_log_path(merged_env)
    timed_out = False
    try:
        with open(os.devnull, "rb") as devnull, open(log_path, "w+b") as logf:
            try:
                proc = subprocess.run(
                    run_cmd,
                    env=merged_env,
                    timeout=timeout_sec,
                    stdin=devnull,
                    stdout=logf,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
                code = proc.returncode
            except subprocess.TimeoutExpired:
                code, timed_out = -1, True
            logf.flush()
            logf.seek(0)
            output = logf.read().decode("utf-8", "replace")
    except OSError as exc:
        return 127, "", str(exc)
    finally:
        try:
            os.unlink(log_path)
        except OSError:
            pass
    if timed_out:
        output += "\nExecution timed out."
    # Output is combined into stderr so existing display/classification (which
    # read stderr) keep working.
    return code, "", output


def _read_gui_log(logf) -> str:
    logf.flush()
    logf.seek(0)
    return logf.read().decode("utf-8", "replace")


def _run_gui_detach(
    run_cmd: List[str],
    merged_env: Dict[str, str],
    *,
    bootstrap_sec: int,
    max_wait_sec: int,
) -> Tuple[int, str, str]:
    """Start a Wine GUI launcher and detach once it survives bootstrap.

    Long-running Electron launchers were falsely marked failed when
    subprocess.run hit execution_timeout_sec and killed the process.
    """
    log_path = _gui_log_path(merged_env)
    proc: Optional[subprocess.Popen] = None
    try:
        with open(os.devnull, "rb") as devnull, open(log_path, "w+b") as logf:
            proc = subprocess.Popen(
                run_cmd,
                env=merged_env,
                stdin=devnull,
                stdout=logf,
                stderr=subprocess.STDOUT,
            )
            started = time.monotonic()
            output = ""
            while time.monotonic() - started < max_wait_sec:
                code = proc.poll()
                output = _read_gui_log(logf)
                lower = output.lower()
                if "bad option:" in lower or "unknown option" in lower:
                    _terminate_process(proc)
                    return 1, "", output

                if code is not None:
                    return code, "", output

                if time.monotonic() - started >= bootstrap_sec:
                    time.sleep(5.0)
                    output = _read_gui_log(logf)
                    fail_sig = launch_failure_in_log(output, "")
                    prefix = merged_env.get("WINEPREFIX", "")
                    if not fail_sig and prefix and wine_rundll32_active(prefix):
                        fail_sig = "dotnet_missing"
                        output += (
                            "\n[Alma] Detected rundll32.exe during bootstrap — "
                            ".NET repair required.\n"
                        )
                    if fail_sig:
                        _terminate_process(proc)
                        return 1, "", output
                    return (
                        0,
                        "",
                        output
                        + "\n[Alma] GUI detached — process still running after "
                        f"{bootstrap_sec}s bootstrap.",
                    )

                time.sleep(1.0)

            output = _read_gui_log(logf)
            _terminate_process(proc)
            return -1, "", output + "\nExecution timed out."
    except OSError as exc:
        if proc is not None:
            _terminate_process(proc)
        return 127, "", str(exc)
    finally:
        try:
            os.unlink(log_path)
        except OSError:
            pass


def _terminate_process(proc: subprocess.Popen) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:  # noqa: BLE001
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass
