"""Unified automation orchestrator: scan → assess → playbook → apply → verify → bridge → learn."""

from __future__ import annotations

import platform
import socket
from typing import Any, Dict, List, Optional

from alma_bridge.automation.approval import consume_approval_token, create_approval_token
from alma_bridge.automation.events import emit_event
from alma_bridge.automation.playbooks import build_recipe_playbook, list_playbooks
from alma_bridge.automation.scanlite import scan_lite
from alma_bridge.automation.sessions import (
    finalize_automation_session,
    get_automation_session,
    list_automation_sessions,
    new_automation_session,
)
from alma_bridge.compliance.program import redact_request_payload
from alma_bridge.automation.verify import verify_modernization
from alma_bridge.compliance.autopilot import record_outcome
from alma_bridge.compliance.modernization import (
    apply_playbook_steps,
    assess_host,
    build_modernization_playbook,
)
from alma_bridge.execution.privileges import prepare_sudo
from alma_bridge.schemas.models import BridgeRequest


def machine_health() -> Dict[str, Any]:
    """Aggregate view for the machine health dashboard."""
    assessment = assess_host()
    sessions = list_automation_sessions(limit=5)
    last = sessions[0] if sessions else None
    return {
        "hostname": socket.gethostname(),
        "machine": platform.machine(),
        "verdict": assessment.get("verdict"),
        "potato_score": assessment.get("potato_score"),
        "gaps": assessment.get("gaps", []),
        "summary": assessment.get("summary"),
        "browsers": assessment.get("browsers"),
        "browser_recommendation": assessment.get("browser_recommendation"),
        "hardware": assessment.get("hardware"),
        "last_automation": last,
        "recent_sessions": sessions,
    }


def run_automation(
    *,
    scan_path: Optional[str] = None,
    playbook_recipe: Optional[str] = None,
    apply: bool = False,
    allow_mutations: bool = False,
    approval_token: Optional[str] = None,
    sudo_password: Optional[str] = None,
    step_ids: Optional[List[str]] = None,
    verify: bool = True,
    https_probe_host: str = "example.com",
    file_path: Optional[str] = None,
    bridge_run: bool = False,
    bridge_max_attempts: int = 4,
    bridge_sandbox: bool = False,
    error_text: Optional[str] = None,
    os_release: Optional[str] = None,
    container_run: bool = False,
) -> Dict[str, Any]:
    """Execute the full automation pipeline and persist an audit session."""
    from alma_bridge.execution.privileges import get_stored_sudo_password, remember_sudo_password

    if sudo_password:
        remember_sudo_password(sudo_password)
    else:
        sudo_password = get_stored_sudo_password()

    hostname = socket.gethostname()
    request_snapshot = redact_request_payload(
        {
            "scan_path": scan_path,
            "playbook_recipe": playbook_recipe,
            "apply": apply,
            "allow_mutations": allow_mutations,
            "file_path": file_path,
            "bridge_run": bridge_run,
            "verify": verify,
        }
    )
    session_id = new_automation_session(hostname=hostname, request=request_snapshot)
    phases: List[Dict[str, Any]] = []
    success = True

    try:
        # 1 — Scan
        if scan_path:
            scan_result = scan_lite(scan_path)
            phases.append({"phase": "scan", "ok": scan_result.get("ok", False), "data": scan_result})
            if not scan_result.get("ok"):
                success = False

        # 2 — Assess
        assessment = assess_host(os_release=os_release)
        phases.append({"phase": "assess", "ok": True, "data": assessment})

        # 3 — Playbook
        if playbook_recipe == "container-lab" and file_path:
            from alma_bridge.execution.shim_pack import build_shim_pack, run_shim_pack

            pack = build_shim_pack(
                file_path,
                error_signature=error_text.split("\n")[0][:80] if error_text else None,
            )
            phases.append({
                "phase": "container_shim_pack",
                "ok": pack.get("ok", False),
                "data": {k: v for k, v in pack.items() if k not in {"stdout", "stderr"}},
            })
            if not pack.get("ok"):
                success = False
            elif container_run:
                exec_result = run_shim_pack(
                    file_path,
                    error_signature=error_text.split("\n")[0][:80] if error_text else None,
                )
                phases.append({
                    "phase": "container_run",
                    "ok": exec_result.get("success", False),
                    "data": {
                        k: v
                        for k, v in exec_result.items()
                        if k in {
                            "success", "exit_code", "sandbox_ready", "shims",
                            "command", "container_spec", "notes", "stdout", "stderr",
                        }
                    },
                })
                if not exec_result.get("success"):
                    success = False
            playbook = build_recipe_playbook("container-lab", assessment, os_release=os_release)
        elif playbook_recipe:
            playbook = build_recipe_playbook(playbook_recipe, assessment, os_release=os_release)
        else:
            playbook = build_modernization_playbook(assessment, os_release=os_release)
        phases.append({"phase": "playbook", "ok": True, "data": {
            k: playbook[k] for k in (
                "verdict", "potato_score", "gaps", "summary",
                "apply_step_ids", "recipe_id", "recipe_title", "recipe_description",
                "classroom_notes", "school_lab", "steps",
            ) if k in playbook
        }})

        apply_results: List[Dict[str, Any]] = []
        verify_result: Optional[Dict[str, Any]] = None

        # 4 — Apply
        if apply:
            if not allow_mutations and not approval_token:
                phases.append({
                    "phase": "apply",
                    "ok": False,
                    "error": "allow_mutations or approval_token required",
                })
                success = False
            else:
                target_steps = step_ids or playbook.get("apply_step_ids")
                if approval_token:
                    ok, err = consume_approval_token(approval_token, target_steps)
                    if not ok:
                        phases.append({"phase": "apply", "ok": False, "error": err})
                        success = False
                    else:
                        apply_results = _do_apply(
                            playbook, target_steps, sudo_password=sudo_password,
                            package_manager=playbook.get("package_manager"),
                        )
                else:
                    sudo_ok, sudo_err = prepare_sudo(
                        requested=True, password=sudo_password
                    )
                    if not sudo_ok:
                        phases.append({"phase": "apply", "ok": False, "error": sudo_err})
                        success = False
                    else:
                        apply_results = _do_apply(
                            playbook, target_steps, sudo_password=sudo_password,
                            package_manager=playbook.get("package_manager"),
                        )

                apply_ok = all(r.get("ok") for r in apply_results) if apply_results else False
                phases.append({
                    "phase": "apply",
                    "ok": apply_ok,
                    "data": {"results": apply_results},
                })
                if not apply_ok:
                    success = False

                # 5 — Verify
                if verify and apply_results:
                    verify_result = verify_modernization(
                        before=assessment,
                        apply_results=apply_results,
                        https_probe_host=https_probe_host,
                    )
                    phases.append({
                        "phase": "verify",
                        "ok": verify_result.get("verified", False),
                        "data": {k: v for k, v in verify_result.items() if k != "after_assessment"},
                    })
                    if verify_result.get("verified"):
                        record_outcome("host_modernization", "full_playbook", True)
                    else:
                        record_outcome("host_modernization", "full_playbook", False)
                        success = False

        # 6 — Bridge (optional)
        if file_path and bridge_run:
            from alma_bridge.learning.orchestrator import BridgeOrchestrator

            orch = BridgeOrchestrator()
            bridge_req = BridgeRequest(
                file_path=file_path,
                max_attempts=bridge_max_attempts,
                sandbox=bridge_sandbox,
                use_sudo=bool(sudo_password),
                sudo_password=sudo_password,
            )
            bridge_result = orch.run(bridge_req, session_id=f"auto-{session_id[:8]}")
            phases.append({
                "phase": "bridge",
                "ok": bridge_result.success,
                "data": {
                    "session_id": bridge_result.session_id,
                    "success": bridge_result.success,
                    "summary": bridge_result.summary,
                },
            })
            if not bridge_result.success:
                success = False

        # 7 — Autopilot for error_text (optional, plan-only unless apply)
        if error_text:
            from alma_bridge.compliance.autopilot import run_autopilot

            autopilot = run_autopilot(
                error_text,
                os_release=os_release,
                execute=apply and allow_mutations,
                allow_mutations=apply and allow_mutations,
            )
            phases.append({"phase": "autopilot", "ok": True, "data": autopilot})

        final_assessment = (
            verify_result.get("after_assessment") if verify_result else assess_host(os_release=os_release)
        )
        summary = _build_summary(phases, final_assessment)

        finalize_automation_session(
            session_id,
            success=success,
            verdict=final_assessment.get("verdict"),
            potato_score=final_assessment.get("potato_score"),
            summary=summary,
            phases=phases,
        )

        emit_event("automation.completed", {
            "session_id": session_id,
            "success": success,
            "verdict": final_assessment.get("verdict"),
        })

        return {
            "session_id": session_id,
            "success": success,
            "summary": summary,
            "phases": phases,
            "health": {
                "verdict": final_assessment.get("verdict"),
                "potato_score": final_assessment.get("potato_score"),
                "gaps": final_assessment.get("gaps", []),
            },
        }
    except Exception as exc:  # noqa: BLE001
        finalize_automation_session(
            session_id,
            success=False,
            verdict=None,
            potato_score=None,
            summary=str(exc),
            phases=phases,
        )
        raise


def _do_apply(
    playbook: Dict[str, Any],
    step_ids: Optional[List[str]],
    *,
    sudo_password: Optional[str],
    package_manager: Optional[str],
) -> List[Dict[str, Any]]:
    outcome = apply_playbook_steps(
        playbook["steps"],
        step_ids=step_ids,
        allow_mutations=True,
        stop_on_error=True,
        package_manager=package_manager,
        sudo_password=sudo_password,
    )
    return outcome.get("results") or []


def _build_summary(phases: List[Dict[str, Any]], assessment: Dict[str, Any]) -> str:
    parts = [f"Automation finished — verdict {assessment.get('verdict')}."]
    for phase in phases:
        name = phase.get("phase")
        status = "ok" if phase.get("ok") else "failed"
        parts.append(f"{name}: {status}")
    return " ".join(parts)


def request_approval(step_ids: List[str], *, ttl_minutes: int = 30) -> Dict[str, Any]:
    return create_approval_token(step_ids, ttl_minutes=ttl_minutes)
