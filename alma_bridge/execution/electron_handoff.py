from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from alma_bridge.execution.errors import RECOMMENDED_ACTIONS, detect_error_signature, launch_failure_in_log
from alma_bridge.execution.wine_process import (
    wait_for_main_launcher_process,
    wine_has_main_launcher_process,
    wine_rundll32_active,
)

CLIENT_SERVICES_MARKERS = (
    "launching elevated",
    "clientservices",
    "client-services",
)

CLIENT_SERVICES_SUCCESS_MARKERS = (
    "listening on",
    "server started",
    "sidecar ready",
    "client services ready",
    "connected to client",
)

BENIGN_ELECTRON_WINE_MARKERS = (
    "wsalookupservicebegin failed with: 8",
    "network_change_notifier_win.cc",
)

POST_HANDOFF_SURVIVAL_SEC = 8.0
POST_HANDOFF_WATCH_SEC = 30.0
SIDECAR_SILENT_CRASH_SEC = 10.0

REAL_EXE_MARKERS = (
    ".real.exe",
    "clientservices.real.exe",
)


def _sidecar_output_log(wine_prefix: str) -> Path:
    return Path(wine_prefix).expanduser() / "drive_c" / "alma-cs-output.log"


def _sidecar_invoke_log(wine_prefix: str) -> Path:
    return Path(wine_prefix).expanduser() / "drive_c" / "alma-cs-invoke.log"


def sidecar_produced_output(wine_prefix: str) -> bool:
    """True when Alma's cs_wrapper captured sidecar stdout/stderr."""
    path = _sidecar_output_log(wine_prefix)
    return path.is_file() and path.stat().st_size > 0


def sidecar_exited_successfully(wine_prefix: str) -> bool:
    """True when the latest wrapper log line reports a clean sidecar exit."""
    path = _sidecar_invoke_log(wine_prefix)
    if not path.is_file() or not path.stat().st_size:
        return False
    try:
        tail = path.read_text(encoding="utf-8", errors="replace")[-2000:]
    except OSError:
        return False
    for line in reversed(tail.splitlines()):
        lower = line.lower()
        if "sidecar exited code=0" in lower:
            return True
        if "sidecar exited code=" in lower:
            return False
    return False


def client_services_handoff_verified(wine_prefix: str, stderr: str) -> bool:
    """Positive proof the elevated sidecar came up — not just bootstrap noise."""
    combined = (stderr or "").lower()
    if any(marker in combined for marker in CLIENT_SERVICES_SUCCESS_MARKERS):
        return True
    if sidecar_produced_output(wine_prefix):
        return True
    return sidecar_exited_successfully(wine_prefix)


def reached_client_services_phase(stderr: str) -> bool:
    return any(marker in (stderr or "").lower() for marker in CLIENT_SERVICES_MARKERS)


def _sidecar_output_size(wine_prefix: str) -> int:
    path = _sidecar_output_log(wine_prefix)
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def _sidecar_invoke_size(wine_prefix: str) -> int:
    path = _sidecar_invoke_log(wine_prefix)
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def _read_invoke_bytes_since(wine_prefix: str, offset: int) -> str:
    path = _sidecar_invoke_log(wine_prefix)
    if not path.is_file():
        return ""
    try:
        with path.open("rb") as handle:
            handle.seek(max(0, offset))
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _recent_invoke_text(wine_prefix: str, tail_bytes: int = 4096) -> str:
    path = _sidecar_invoke_log(wine_prefix)
    if not path.is_file():
        return ""
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            handle.seek(max(0, size - tail_bytes))
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def sidecar_real_exe_invoked(wine_prefix: str, *, since_invoke_size: int = 0) -> bool:
    """True when the wrapper logged a launch of the real sidecar binary."""
    chunk = _read_invoke_bytes_since(wine_prefix, since_invoke_size).lower()
    if any(marker in chunk for marker in REAL_EXE_MARKERS):
        return True
    if since_invoke_size == 0:
        recent = _recent_invoke_text(wine_prefix).lower()
        return any(marker in recent for marker in REAL_EXE_MARKERS)
    return False


def watch_sidecar_handoff(
    wine_prefix: str,
    *,
    watch_sec: float = POST_HANDOFF_WATCH_SEC,
    silent_crash_sec: float = SIDECAR_SILENT_CRASH_SEC,
    poll_sec: float = 0.5,
) -> Tuple[Optional[str], str]:
    """Poll sidecar logs after client-services handoff begins.

    Returns ``(signature, detail)``. ``signature`` is ``None`` when the sidecar
    produced verifiable progress.
    """
    baseline_output = _sidecar_output_size(wine_prefix)
    invoke_mark = _sidecar_invoke_size(wine_prefix)
    deadline = time.monotonic() + watch_sec
    silent_deadline: Optional[float] = None
    saw_real_exe = sidecar_real_exe_invoked(wine_prefix)
    if saw_real_exe:
        silent_deadline = time.monotonic() + silent_crash_sec

    while time.monotonic() < deadline:
        if client_services_handoff_verified(wine_prefix, ""):
            return None, "Sidecar handoff verified during watchdog."

        if _sidecar_output_size(wine_prefix) > baseline_output:
            return None, "Sidecar output log is growing."

        invoke_size = _sidecar_invoke_size(wine_prefix)
        if invoke_size > invoke_mark:
            if sidecar_real_exe_invoked(wine_prefix, since_invoke_size=invoke_mark):
                saw_real_exe = True
                if silent_deadline is None:
                    silent_deadline = time.monotonic() + silent_crash_sec
            invoke_mark = invoke_size

        if saw_real_exe and silent_deadline and time.monotonic() >= silent_deadline:
            if _sidecar_output_size(wine_prefix) <= baseline_output:
                detail = (
                    "Sidecar .real.exe was invoked but produced no output within "
                    f"{int(silent_crash_sec)}s."
                )
                return "sidecar_silent_crash", detail

        time.sleep(poll_sec)

    if saw_real_exe and _sidecar_output_size(wine_prefix) <= baseline_output:
        return (
            "sidecar_silent_crash",
            f"Sidecar .real.exe ran but alma-cs-output.log stayed empty after {int(watch_sec)}s.",
        )
    return (
        "client_services_stalled",
        f"No sidecar progress within {int(watch_sec)}s after handoff.",
    )


def append_sidecar_logs(wine_prefix: str, stderr: str) -> str:
    """Attach Alma sidecar wrapper logs when present."""
    drive_c = Path(wine_prefix).expanduser() / "drive_c"
    chunks = [stderr or ""]
    for name in ("alma-cs-output.log", "alma-cs-invoke.log"):
        path = drive_c / name
        if path.is_file() and path.stat().st_size:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")[-4000:]
                chunks.append(f"\n[Alma] {name} tail:\n{text}")
            except OSError:
                pass
    return "".join(chunks).strip()


def format_electron_launch_stderr(stderr: str, *, success: bool) -> str:
    if not stderr or not success:
        return stderr
    if not any(marker in stderr.lower() for marker in BENIGN_ELECTRON_WINE_MARKERS):
        return stderr
    return (
        "Launcher process started. The WSALookupServiceBegin / network_change_notifier "
        "messages below are normal Wine noise under Electron — not a failed launch.\n\n"
        + stderr
    )


def detect_electron_launcher_failure(
    stderr: str,
    stdout: str,
    *,
    exit_code: Optional[int],
    wine_prefix: Optional[str] = None,
) -> Optional[str]:
    combined = f"{stderr or ''}\n{stdout or ''}".lower()
    if any(marker in combined for marker in CLIENT_SERVICES_SUCCESS_MARKERS):
        return None
    # Sidecar stall beats incidental Crashpad log lines when disable flags are already set.
    if exit_code not in (None, 0) and reached_client_services_phase(combined):
        if wine_prefix is None or not client_services_handoff_verified(wine_prefix, combined):
            return "client_services_stalled"
    signature = detect_error_signature(stderr, stdout)
    if signature != "unknown_error":
        return signature
    return None


def evaluate_electron_launch_result(
    result: Dict[str, object],
    *,
    wine_prefix: str,
    launcher_path: str,
    wait_sec: float = 12.0,
    exclude_pids: Optional[set[int]] = None,
) -> Tuple[Dict[str, object], Optional[str], List[str]]:
    """Re-evaluate a Wine/Electron launch that may have detached or stalled."""
    stderr = append_sidecar_logs(wine_prefix, str(result.get("stderr", "")))
    stdout = str(result.get("stdout", ""))
    exit_code = result.get("exit_code")
    updated: Dict[str, object] = {**result, "stderr": stderr}
    pid_skip = set(exclude_pids or ())

    if updated.get("success") and updated.get("launch_verification"):
        updated["stderr"] = format_electron_launch_stderr(str(updated["stderr"]), success=True)
        return updated, None, list(updated.get("launch_verification") or [])

    if updated.get("success"):
        updated = {**updated, "success": False}

    log_fail = launch_failure_in_log(stderr, stdout)
    if log_fail:
        return (
            updated,
            log_fail,
            list(RECOMMENDED_ACTIONS.get(log_fail, RECOMMENDED_ACTIONS["unknown_error"])),
        )

    if wine_rundll32_active(wine_prefix):
        stderr = (
            f"{stderr}\n\n[Alma] Detected rundll32.exe in Wine prefix — "
            ".NET bootstrap dialog likely appeared (not always captured in logs).\n"
        )
        updated["stderr"] = stderr
        return (
            updated,
            "dotnet_missing",
            list(RECOMMENDED_ACTIONS.get("dotnet_missing", RECOMMENDED_ACTIONS["unknown_error"])),
        )

    combined = f"{stderr}\n{stdout}".lower()
    if (
        "executing:" in combined
        and "ascension-setup" in combined
        and ".exe" in combined
    ):
        stderr = (
            f"{stderr}\n\n[Alma] Electron auto-updater launched ascension-setup inside Wine — "
            "this triggers rundll32/.NET bootstrap. Bridge will disable auto-update on retry.\n"
        )
        updated["stderr"] = stderr
        return (
            updated,
            "dotnet_missing",
            list(RECOMMENDED_ACTIONS.get("dotnet_missing", RECOMMENDED_ACTIONS["unknown_error"])),
        )

    signature = detect_electron_launcher_failure(
        stderr,
        stdout,
        exit_code=exit_code,  # type: ignore[arg-type]
        wine_prefix=wine_prefix,
    )
    handoff_verified = client_services_handoff_verified(wine_prefix, stderr)
    saw_client_services = reached_client_services_phase(stderr)

    if saw_client_services and not handoff_verified:
        watch_sig, watch_detail = watch_sidecar_handoff(wine_prefix)
        stderr = f"{stderr}\n\n[Alma] Sidecar watchdog: {watch_detail}\n"
        updated["stderr"] = stderr
        if watch_sig is None:
            handoff_verified = client_services_handoff_verified(wine_prefix, stderr)
        else:
            signature = watch_sig

    if signature and not handoff_verified:
        return (
            updated,
            signature,
            list(RECOMMENDED_ACTIONS.get(signature, RECOMMENDED_ACTIONS["unknown_error"])),
        )

    # Bootstrap can keep the main launcher alive for several seconds while the
    # elevated sidecar fails — never treat that alone as success.
    process_success_allowed = signature != "client_services_stalled" and (
        exit_code in (None, 0) or handoff_verified or not saw_client_services
    )

    if process_success_allowed and wait_for_main_launcher_process(
        wine_prefix,
        launcher_path,
        timeout_sec=wait_sec,
        exclude_pids=pid_skip,
    ):
        hold_sec = POST_HANDOFF_SURVIVAL_SEC if saw_client_services else 3.0
        time.sleep(hold_sec)
        if wine_has_main_launcher_process(
            wine_prefix, launcher_path, exclude_pids=pid_skip
        ):
            log_fail = launch_failure_in_log(stderr, stdout)
            if log_fail:
                return (
                    updated,
                    log_fail,
                    list(RECOMMENDED_ACTIONS.get(log_fail, RECOMMENDED_ACTIONS["unknown_error"])),
                )
            if saw_client_services and not handoff_verified:
                signature = signature or "client_services_stalled"
            else:
                verification = [
                    f"{Path(launcher_path).name} is running from the install directory "
                    "(not Alma's alma-guard decoy)."
                ]
                if exit_code not in (None, 0):
                    verification.append(
                        "Bootstrap exited non-zero, but the main launcher process is still alive — "
                        "check your desktop for the Ascension window."
                    )
                if handoff_verified:
                    verification.append("Elevated client-services sidecar produced output.")
                updated = {
                    **updated,
                    "success": True,
                    "stderr": format_electron_launch_stderr(stderr, success=True),
                    "launch_verification": verification,
                }
                return updated, None, verification

    if signature:
        return (
            updated,
            signature,
            list(RECOMMENDED_ACTIONS.get(signature, RECOMMENDED_ACTIONS["unknown_error"])),
        )

    return updated, signature or "unknown_error", list(RECOMMENDED_ACTIONS["unknown_error"])
