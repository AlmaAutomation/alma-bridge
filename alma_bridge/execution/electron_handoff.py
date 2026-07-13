from __future__ import annotations

import re
import time
from dataclasses import dataclass
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

# Sidecar handoff evidence contract (electron_handoff verifier).
# v1.0.0: required alma-cs-output.log growth or exact "sidecar exited code=0" substring.
# v1.1.0: parse current + legacy wrapper exit lines; require corroboration before handoff pass.
SIDECAR_HANDOFF_CONTRACT_VERSION = "1.1.0"

_CURRENT_WRAPPER_EXIT_RE = re.compile(
    r"\[cs-wrapper\]\s*sidecar exited code=(\d+)",
    re.IGNORECASE,
)
_LEGACY_WRAPPER_EXIT_RE = re.compile(
    r"\[cs-wrapper\]\s*real client-services exited with code\s+(\d+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SidecarHandoffEvidence:
    """Structured evidence parsed from Alma sidecar wrapper logs."""

    contract_version: str
    real_exe_invoked: bool
    wrapper_exit_code: Optional[int]
    wrapper_log_format: Optional[str]
    decoy_spawned: bool
    invoke_bytes: int
    output_bytes: int
    output_has_success_marker: bool
    stderr_has_success_marker: bool

    @property
    def wrapper_reported_clean_exit(self) -> bool:
        return self.wrapper_exit_code == 0

    def to_evidence_lines(self) -> List[str]:
        lines = [
            f"handoff_contract={self.contract_version}",
            f"real_exe_invoked={self.real_exe_invoked}",
            f"wrapper_exit_code={self.wrapper_exit_code}",
            f"wrapper_log_format={self.wrapper_log_format}",
            f"decoy_spawned={self.decoy_spawned}",
            f"invoke_bytes={self.invoke_bytes}",
            f"output_bytes={self.output_bytes}",
        ]
        return lines


def _sidecar_output_log(wine_prefix: str) -> Path:
    return Path(wine_prefix).expanduser() / "drive_c" / "alma-cs-output.log"


def _sidecar_invoke_log(wine_prefix: str) -> Path:
    return Path(wine_prefix).expanduser() / "drive_c" / "alma-cs-invoke.log"


def sidecar_produced_output(wine_prefix: str) -> bool:
    """True when Alma's cs_wrapper captured sidecar stdout/stderr."""
    path = _sidecar_output_log(wine_prefix)
    return path.is_file() and path.stat().st_size > 0


def _output_has_success_marker(wine_prefix: str) -> bool:
    path = _sidecar_output_log(wine_prefix)
    if not path.is_file() or not path.stat().st_size:
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return False
    return any(marker in text for marker in CLIENT_SERVICES_SUCCESS_MARKERS)


def _stderr_has_success_marker(stderr: str) -> bool:
    combined = (stderr or "").lower()
    return any(marker in combined for marker in CLIENT_SERVICES_SUCCESS_MARKERS)


def _parse_wrapper_exit_code(invoke_text: str) -> Tuple[Optional[int], Optional[str]]:
    for line in reversed(invoke_text.splitlines()):
        current = _CURRENT_WRAPPER_EXIT_RE.search(line)
        if current:
            return int(current.group(1)), "current_cs_wrapper"
        legacy = _LEGACY_WRAPPER_EXIT_RE.search(line)
        if legacy:
            return int(legacy.group(1)), "legacy_cs_wrapper"
        lower = line.lower()
        if "sidecar exited code=" in lower and "code=0" not in lower:
            return 1, "current_cs_wrapper"
        if "real client-services exited with code" in lower and "code 0" not in lower:
            return 1, "legacy_cs_wrapper"
    return None, None


def parse_sidecar_handoff_evidence(
    wine_prefix: str,
    stderr: str = "",
) -> SidecarHandoffEvidence:
    """Parse sidecar invoke/output logs into structured handoff evidence."""
    invoke_text = _recent_invoke_text(wine_prefix)
    invoke_lower = invoke_text.lower()
    exit_code, log_format = _parse_wrapper_exit_code(invoke_text)
    decoy_match = re.search(r"decoy_pid=([1-9]\d*)", invoke_lower)
    return SidecarHandoffEvidence(
        contract_version=SIDECAR_HANDOFF_CONTRACT_VERSION,
        real_exe_invoked=any(marker in invoke_lower for marker in REAL_EXE_MARKERS),
        wrapper_exit_code=exit_code,
        wrapper_log_format=log_format,
        decoy_spawned=bool(decoy_match),
        invoke_bytes=_sidecar_invoke_size(wine_prefix),
        output_bytes=_sidecar_output_size(wine_prefix),
        output_has_success_marker=_output_has_success_marker(wine_prefix),
        stderr_has_success_marker=_stderr_has_success_marker(stderr),
    )


def sidecar_exited_successfully(wine_prefix: str) -> bool:
    """True when the latest wrapper log reports a clean sidecar exit (any supported format)."""
    evidence = parse_sidecar_handoff_evidence(wine_prefix)
    return evidence.wrapper_reported_clean_exit


def _launcher_process_alive(
    wine_prefix: str,
    launcher_path: Optional[str],
    exclude_pids: Optional[set[int]],
) -> bool:
    if not launcher_path:
        return False
    return wine_has_main_launcher_process(
        wine_prefix,
        launcher_path,
        exclude_pids=exclude_pids or set(),
    )


def client_services_handoff_verified(
    wine_prefix: str,
    stderr: str,
    *,
    launcher_path: Optional[str] = None,
    exclude_pids: Optional[set[int]] = None,
) -> bool:
    """Positive proof the elevated sidecar handoff succeeded.

    Exit code 0 alone is insufficient. Requires at least two independent signals
    where possible: wrapper/real.exe evidence plus output, stderr, or launcher survival.
    """
    evidence = parse_sidecar_handoff_evidence(wine_prefix, stderr)

    if evidence.stderr_has_success_marker:
        return True
    if evidence.output_has_success_marker:
        return True
    if evidence.output_bytes > 0 and sidecar_produced_output(wine_prefix):
        return True

    if not evidence.real_exe_invoked:
        return False
    if not evidence.wrapper_reported_clean_exit:
        return False

    corroborations = 0
    if evidence.output_bytes > 0:
        corroborations += 1
    if _launcher_process_alive(wine_prefix, launcher_path, exclude_pids):
        corroborations += 1
    if evidence.decoy_spawned:
        corroborations += 1

    return corroborations >= 1


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
    launcher_path: Optional[str] = None,
    exclude_pids: Optional[set[int]] = None,
    stderr: str = "",
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
        if client_services_handoff_verified(
            wine_prefix,
            stderr,
            launcher_path=launcher_path,
            exclude_pids=exclude_pids,
        ):
            evidence = parse_sidecar_handoff_evidence(wine_prefix, stderr)
            return None, (
                "Sidecar handoff verified during watchdog "
                f"({', '.join(evidence.to_evidence_lines())})."
            )

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
                if client_services_handoff_verified(
                    wine_prefix,
                    stderr,
                    launcher_path=launcher_path,
                    exclude_pids=exclude_pids,
                ):
                    evidence = parse_sidecar_handoff_evidence(wine_prefix, stderr)
                    return None, (
                        "Sidecar handoff corroborated at silent-crash deadline "
                        f"({', '.join(evidence.to_evidence_lines())})."
                    )
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
    handoff_verified = client_services_handoff_verified(
        wine_prefix,
        stderr,
        launcher_path=launcher_path,
        exclude_pids=pid_skip,
    )
    saw_client_services = reached_client_services_phase(stderr)

    if saw_client_services and not handoff_verified:
        watch_sig, watch_detail = watch_sidecar_handoff(
            wine_prefix,
            launcher_path=launcher_path,
            exclude_pids=pid_skip,
            stderr=stderr,
        )
        stderr = f"{stderr}\n\n[Alma] Sidecar watchdog: {watch_detail}\n"
        updated["stderr"] = stderr
        if watch_sig is None:
            handoff_verified = client_services_handoff_verified(
                wine_prefix,
                stderr,
                launcher_path=launcher_path,
                exclude_pids=pid_skip,
            )
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
                    handoff_evidence = parse_sidecar_handoff_evidence(wine_prefix, stderr)
                    verification.extend(
                        ["Elevated client-services sidecar handoff verified."]
                        + handoff_evidence.to_evidence_lines()
                    )
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
