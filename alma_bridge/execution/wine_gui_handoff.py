from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from alma_bridge.compatibility.framework_detection import detect_gui_framework
from alma_bridge.config import settings
from alma_bridge.execution.errors import (
    detect_error_signature,
    is_single_instance_message,
    launch_failure_in_log,
)
from alma_bridge.execution.wine_process import (
    observe_target_gui_process,
    wine_rundll32_active,
)

WINE_GUI_HANDOFF_CONTRACT_VERSION = "wine_gui_process_v2"
WXWIDGETS_READINESS_CONTRACT_VERSION = "wxwidgets_readiness_v1"


def evaluate_wxwidgets_readiness(stderr: str, stdout: str = "") -> Tuple[bool, List[str]]:
    """Aggregate wxWidgets startup readiness from runtime logs."""
    combined = f"{stderr or ''}\n{stdout or ''}"
    lower = combined.lower()
    evidence: List[str] = []

    has_banner = "wxwidgets" in lower
    if has_banner:
        evidence.append("wxwidgets_runtime_banner=true")

    markers = {
        "manager_initialized": "manager initialized" in lower,
        "compiler_plugin_activated": (
            "compiler plugin activated" in lower or "compiler: loaded" in lower
        ),
        "compiler_detection_progress": (
            "compiler detection" in lower
            or "master path of compiler" in lower
            or "final mingw master path" in lower
        ),
    }
    for name, present in markers.items():
        if present:
            evidence.append(f"{name}=true")

    corroborating = [name for name, present in markers.items() if present]
    if has_banner and not corroborating:
        evidence.append("splash_only_insufficient=true")
        return False, evidence

    if corroborating:
        evidence.append(
            f"wxwidgets_readiness_contract={WXWIDGETS_READINESS_CONTRACT_VERSION}"
        )
        return True, evidence

    if has_banner:
        evidence.append("splash_only_insufficient=true")
        return False, evidence

    return False, evidence + ["wxwidgets_readiness_missing=true"]


def evaluate_wine_gui_launch_result(
    result: Dict[str, object],
    *,
    wine_prefix: str,
    target_path: str,
    exclude_pids: Optional[Set[int]] = None,
    startup_timeout_sec: Optional[float] = None,
    survival_sec: Optional[float] = None,
    framework: Optional[str] = None,
) -> Tuple[Dict[str, object], Optional[str], List[str]]:
    """Re-evaluate an ordinary Wine GUI launch after detach or supervised start."""
    stderr = str(result.get("stderr", ""))
    stdout = str(result.get("stdout", ""))
    exit_code = result.get("exit_code")
    updated: Dict[str, object] = {**result, "stderr": stderr}
    pid_skip = set(exclude_pids or ())

    detected_framework = framework
    if not detected_framework or detected_framework == "unknown":
        detection = detect_gui_framework(target_path, runtime_log=stderr)
        detected_framework = detection.framework

    startup = startup_timeout_sec or settings.wine_gui_startup_timeout_sec
    survival = survival_sec or settings.wine_gui_survival_sec

    if is_single_instance_message(stderr, stdout):
        observation = observe_target_gui_process(
            wine_prefix,
            target_path,
            exclude_pids=pid_skip,
            startup_timeout_sec=startup,
            survival_sec=survival,
        )
        if observation.appeared and observation.survived:
            verification = observation.to_evidence_lines() + [
                f"handoff_contract={WINE_GUI_HANDOFF_CONTRACT_VERSION}",
                f"target_executable={Path(target_path).name}",
                "process_survives=true",
                f"framework={detected_framework or 'unknown'}",
                "single_instance_guard=true",
                "existing_target_process=true",
            ]
            updated = {
                **updated,
                "success": True,
                "launch_verification": verification,
                "wine_gui_process": observation.to_dict(),
            }
            return updated, None, verification
        return updated, "single_instance_detected", [
            f"target={Path(target_path).name}",
            "single_instance_guard_blocked_launch",
        ]

    detached = "[alma] launcher detached" in stderr.lower() or "[alma] gui detached" in stderr.lower()
    if not detached and not updated.get("success"):
        log_fail = launch_failure_in_log(stderr, stdout)
        if log_fail:
            return updated, log_fail, []
        signature = detect_error_signature(stderr, stdout)
        if signature:
            return updated, signature, []

    if wine_rundll32_active(wine_prefix):
        stderr = (
            f"{stderr}\n\n[Alma] Detected rundll32.exe in Wine prefix during GUI bootstrap.\n"
        )
        updated["stderr"] = stderr
        return updated, "dotnet_missing", []

    observation = observe_target_gui_process(
        wine_prefix,
        target_path,
        exclude_pids=pid_skip,
        startup_timeout_sec=startup,
        survival_sec=survival,
    )

    if not observation.appeared:
        return updated, "gui_process_not_found", [
            f"target={Path(target_path).name}",
            "startup_timeout_exceeded",
        ]

    if not observation.survived:
        return (
            updated,
            "gui_process_exited_early",
            observation.to_evidence_lines()
            + [f"survival_sec_required={survival}"],
        )

    log_fail = launch_failure_in_log(stderr, stdout)
    if log_fail:
        return updated, log_fail, observation.to_evidence_lines()

    verification = observation.to_evidence_lines() + [
        f"handoff_contract={WINE_GUI_HANDOFF_CONTRACT_VERSION}",
        f"target_executable={Path(target_path).name}",
        "process_survives=true",
        f"framework={detected_framework or 'unknown'}",
    ]

    if detected_framework == "wxwidgets":
        readiness_ok, readiness_evidence = evaluate_wxwidgets_readiness(stderr, stdout)
        verification.extend(readiness_evidence)
        if not readiness_ok:
            return updated, "wxwidgets_readiness_insufficient", verification

    if exit_code not in (None, 0) and detached:
        verification.append(
            "Bootstrap exited non-zero, but the target GUI process remained alive."
        )

    updated = {
        **updated,
        "success": True,
        "launch_verification": verification,
        "wine_gui_process": observation.to_dict(),
    }
    return updated, None, verification
