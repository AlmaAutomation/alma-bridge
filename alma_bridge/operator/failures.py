"""Examine failed automation / bridge attempts and plan mitigations."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from alma_bridge.automation.sessions import get_automation_session, list_automation_sessions
from alma_bridge.compliance.autopilot import diagnose, plan_pathways, run_autopilot
from alma_bridge.config import settings
from alma_bridge.storage import outcomes

_WINDOWS_BINARY_SUFFIXES = (".exe", ".msi", ".bat", ".cmd")
_SUDO_HINTS = (
    "sudo:",
    "a password is required",
    "a terminal is required",
    "no cached credentials",
    "sudo is enabled",
)


def _risk_for_kind(kind: str) -> str:
    if kind in ("bridge", "heal", "modernize_apply"):
        return "medium"
    if kind == "modernize_retry":
        return "medium"
    if kind == "fix_permissions":
        return "low"
    return "low"


def _eligible_mitigation(mitigation: Dict[str, Any], autonomy: str) -> bool:
    from alma_bridge.operator.brain import AUTONOMY_LEVELS, RISK_ORDER, _autonomy

    if autonomy in ("observe", "recommend"):
        return False
    max_risk = RISK_ORDER.get((settings.operator_max_risk or "low").lower(), 0)
    if autonomy == "assisted":
        max_risk = min(max_risk, RISK_ORDER["low"])
    risk = RISK_ORDER.get(mitigation.get("risk", "medium"), 2)
    if risk > max_risk:
        return False
    conf = float(mitigation.get("confidence", 0.75))
    return conf >= float(settings.operator_min_confidence)


def _extract_automation_failure(session: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if session.get("success"):
        return None

    phases = session.get("phases") or []
    request = session.get("request") or {}
    errors: List[str] = []
    failed_steps: List[str] = []
    missing_bridge = False
    scan_path = request.get("scan_path") or ""
    file_path = request.get("file_path") or ""

    for phase in phases:
        name = phase.get("phase")
        if phase.get("ok"):
            continue
        if phase.get("error"):
            errors.append(str(phase["error"]))
        data = phase.get("data") or {}
        if name == "apply":
            for step in data.get("results") or []:
                if not step.get("ok"):
                    sid = step.get("step_id")
                    if sid:
                        failed_steps.append(sid)
                    stderr = (step.get("stderr") or "").strip()
                    if stderr:
                        errors.append(stderr)
        elif name == "verify" and not data.get("verified"):
            errors.append(f"verify failed: {data.get('gaps_opened') or 'post-apply check'}")
        elif name == "bridge" and not phase.get("ok"):
            errors.append(data.get("summary") or "bridge phase failed")

    path_lower = (scan_path or file_path).lower()
    if path_lower.endswith(_WINDOWS_BINARY_SUFFIXES) and not any(
        p.get("phase") == "bridge" for p in phases
    ):
        missing_bridge = True
        target = scan_path or file_path
        errors.append(
            f"Windows binary {target} was referenced but Bridge never ran — "
            "use file_path + bridge_run to execute via Wine/Proton."
        )

    if not errors and not failed_steps and not missing_bridge:
        errors.append(session.get("summary") or "automation failed")

    return {
        "source": "automation",
        "session_id": session.get("session_id"),
        "started_at": session.get("started_at"),
        "summary": session.get("summary"),
        "scan_path": scan_path or None,
        "file_path": file_path or None,
        "failed_step_ids": list(dict.fromkeys(failed_steps)),
        "missing_bridge": missing_bridge,
        "bridge_target": (scan_path or file_path) if missing_bridge else None,
        "error_text": "\n".join(errors[:8]),
    }


def _extract_bridge_failure(session: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if session.get("success"):
        return None

    attempts = session.get("attempts") or []
    errors: List[str] = []
    last_sig: Optional[str] = None

    for attempt in attempts:
        if attempt.get("success"):
            continue
        stderr = (attempt.get("stderr") or attempt.get("detected_error") or "").strip()
        if stderr:
            errors.append(stderr[:500])
        sig = attempt.get("error_signature")
        if sig:
            last_sig = sig

    if not errors:
        errors.append(session.get("summary") or "bridge run failed")

    return {
        "source": "bridge",
        "session_id": session.get("session_id"),
        "started_at": session.get("started_at"),
        "summary": session.get("summary"),
        "file_path": session.get("file_path"),
        "error_signature": last_sig,
        "error_text": "\n".join(errors[:6]),
    }


def _is_sudo_credential_failure(failure: Dict[str, Any]) -> bool:
    err = (failure.get("error_text") or "").lower()
    return any(h in err for h in _SUDO_HINTS) or "no cached credentials" in err


def _later_success_supersedes_failure(failure: Dict[str, Any]) -> bool:
    """True when a newer automation or Bridge session succeeded after this failure."""
    failure_at = failure.get("started_at") or ""
    if not failure_at:
        return False
    for row in list_automation_sessions(limit=30):
        if not row.get("success"):
            continue
        if (row.get("started_at") or "") > failure_at:
            return True
    try:
        outcomes.init_outcome_store()
        failure_path = failure.get("file_path") or ""
        for row in outcomes.list_recent_sessions(limit=50):
            if not row.get("success"):
                continue
            if (row.get("started_at") or "") <= failure_at:
                continue
            row_path = row.get("file_path") or ""
            if failure_path and row_path and not _same_program_path(failure_path, row_path):
                continue
            return True
    except Exception:  # noqa: BLE001 - bridge store optional in tests
        pass
    return False


def _same_program_path(left: str, right: str) -> bool:
    if left == right:
        return True
    return Path(left).name.lower() == Path(right).name.lower()


def examine_failures(*, limit: int = 10) -> Dict[str, Any]:
    """Collect recent failures, diagnose root causes, and propose mitigations."""
    from alma_bridge.execution.privileges import sudo_is_ready
    from alma_bridge.operator.brain import _autonomy

    autonomy = _autonomy()
    failures: List[Dict[str, Any]] = []

    for row in list_automation_sessions(limit=limit):
        if row.get("success"):
            continue
        full = get_automation_session(row["session_id"])
        if not full:
            continue
        item = _extract_automation_failure(full)
        if item:
            failures.append(item)

    try:
        outcomes.init_outcome_store()
        for row in outcomes.list_recent_sessions(limit=limit):
            if row.get("success"):
                continue
            full = outcomes.get_session(row["session_id"])
            if not full:
                continue
            item = _extract_bridge_failure(full)
            if item:
                failures.append(item)
    except Exception:  # noqa: BLE001 - bridge store optional in tests
        pass

    sudo_ready = sudo_is_ready()
    stale_sudo_count = 0
    resolved_sudo_count = 0
    display_failures: List[Dict[str, Any]] = []
    for failure in failures:
        if _is_sudo_credential_failure(failure) and _later_success_supersedes_failure(failure):
            resolved_sudo_count += 1
            continue
        if (
            failure.get("source") == "bridge"
            and _later_success_supersedes_failure(failure)
        ):
            resolved_sudo_count += 1
            continue
        if sudo_ready and _is_sudo_credential_failure(failure):
            failure["stale"] = True
            failure["stale_reason"] = (
                "Sudo credentials are ready — automatic retry pending or click Fix all failures."
            )
            stale_sudo_count += 1
        display_failures.append(failure)
    failures = display_failures
    actionable_failures = [f for f in failures if not f.get("stale")]

    plan_failures = actionable_failures if actionable_failures else failures
    combined_parts = [
        f["error_text"]
        for f in plan_failures
        if f.get("error_text") and not f.get("stale")
    ]
    combined_error = "\n---\n".join(combined_parts[:5])
    diagnoses = diagnose(combined_error) if combined_error else []
    healing = plan_pathways(combined_error) if combined_error else None

    mitigations = _plan_mitigations(
        plan_failures,
        healing,
        diagnoses,
        sudo_ready=sudo_ready,
    )
    for m in mitigations:
        m["auto_eligible"] = _eligible_mitigation(m, autonomy)

    # When only stale sudo logs remain, focus on host apply — skip route discovery.
    if not actionable_failures and stale_sudo_count and sudo_ready:
        mitigations = [
            m
            for m in mitigations
            if m.get("kind") in {"modernize_apply", "heal"}
            and (
                m.get("kind") == "modernize_apply"
                or "sudo" in (m.get("id") or "").lower()
            )
        ]
        for m in mitigations:
            m["auto_eligible"] = _eligible_mitigation(m, autonomy)

    return {
        "failure_count": len(actionable_failures),
        "actionable_failure_count": len(actionable_failures),
        "stale_sudo_failure_count": stale_sudo_count,
        "resolved_sudo_failure_count": resolved_sudo_count,
        "all_clear": len(actionable_failures) == 0 and stale_sudo_count == 0,
        "sudo_ready": sudo_ready,
        "failures": actionable_failures if actionable_failures else failures,
        "combined_error_text": combined_error or None,
        "diagnoses": diagnoses[:5],
        "healing": healing,
        "mitigations": mitigations,
        "auto_mitigation_count": sum(1 for m in mitigations if m.get("auto_eligible")),
    }


def _only_stale_sudo_failures(
    failures: List[Dict[str, Any]],
    *,
    sudo_ready: bool = False,
) -> bool:
    if not failures or not sudo_ready:
        return False
    return all(_is_sudo_credential_failure(f) for f in failures)


def _plan_mitigations(
    failures: List[Dict[str, Any]],
    healing: Optional[Dict[str, Any]],
    diagnoses: List[Dict[str, Any]],
    *,
    sudo_ready: bool = False,
) -> List[Dict[str, Any]]:
    mitigations: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()

    def add(item: Dict[str, Any]) -> None:
        mid = item["id"]
        if mid in seen_ids:
            return
        seen_ids.add(mid)
        item.setdefault("risk", _risk_for_kind(item.get("kind", "")))
        item.setdefault("confidence", 0.78)
        mitigations.append(item)

    for failure in failures:
        err = (failure.get("error_text") or "").lower()

        if failure.get("missing_bridge") and failure.get("bridge_target"):
            target = failure["bridge_target"]
            add({
                "id": f"bridge:{Path(target).name}",
                "kind": "bridge",
                "title": f"Run binary via Bridge — {Path(target).name}",
                "file_path": target,
                "rationale": failure["error_text"].split("\n")[0][:200],
                "confidence": 0.92,
            })

        for step_id in failure.get("failed_step_ids") or []:
            add({
                "id": f"retry:{step_id}",
                "kind": "modernize_retry",
                "title": f"Retry failed modernization step — {step_id}",
                "step_ids": [step_id],
                "rationale": f"Prior apply failed on step {step_id}.",
                "confidence": 0.85 if "sudo" not in err else 0.7,
            })

        if failure.get("source") == "bridge" and failure.get("file_path"):
            fp = failure["file_path"]
            add({
                "id": f"bridge-retry:{Path(fp).name}",
                "kind": "bridge",
                "title": f"Retry Bridge — {Path(fp).name}",
                "file_path": fp,
                "rationale": failure.get("summary") or "Previous Bridge session failed.",
                "confidence": 0.8,
            })

        if any(h in err for h in _SUDO_HINTS):
            add({
                "id": "heal:sudo_credentials",
                "kind": "heal",
                "title": "Restore sudo credentials for automation apply",
                "error_text": failure.get("error_text") or "sudo password required",
                "rationale": "Failures mention sudo/TTL — warm cache or use passwordless sudo.",
                "confidence": 0.75,
                "risk": "low",
            })

        if failure.get("source") == "automation" and _is_sudo_credential_failure(failure):
            add({
                "id": "modernize:apply_host",
                "kind": "modernize_apply",
                "title": "Retry host modernization apply (sudo credentials ready)",
                "rationale": "Prior automation apply failed before any playbook steps ran.",
                "confidence": 0.88,
                "risk": "medium",
            })

        if failure.get("source") == "bridge" and failure.get("file_path"):
            fp = failure["file_path"]
            if "permission denied" in err:
                add({
                    "id": f"fix_permissions:{Path(fp).name}",
                    "kind": "fix_permissions",
                    "title": f"Make binary executable — {Path(fp).name}",
                    "file_path": fp,
                    "rationale": "Bridge could not execute the file — ensure execute permission.",
                    "confidence": 0.9,
                    "risk": "low",
                })

            sig = failure.get("error_signature") or ""
            if (
                sig in {"dotnet_missing", "missing_dll", "missing_visual_c_runtime", "wine_int3_crash"}
                or "rundll32" in err
                or "application could not be started" in err
                or "ascension" in fp.lower()
            ):
                add({
                    "id": f"prefix_bootstrap:{Path(fp).name}",
                    "kind": "prefix_bootstrap",
                    "title": f"AI/ML — repair Wine prefix runtimes for {Path(fp).name}",
                    "file_path": fp,
                    "error_signature": sig or "dotnet_missing",
                    "rationale": (
                        "Bridge detected .NET/rundll32 or Ascension-on-Wine failure — "
                        "auto-repair VC++/dotnet and Electron wrappers."
                    ),
                    "confidence": 0.97,
                    "risk": "medium",
                })

    if healing and healing.get("pathways"):
        top = healing["pathways"][0]
        sig = healing.get("primary_signature") or "unknown"
        add({
            "id": f"heal:{top.get('id', sig)}",
            "kind": "heal",
            "title": f"Self-heal — {top.get('title', sig)}",
            "error_text": "\n".join(
                f["error_text"] for f in failures if f.get("error_text")
            )[:2000],
            "pathway_id": top.get("id"),
            "signature": sig,
            "rationale": f"Autopilot ranked pathway for signature '{sig}'.",
            "confidence": round(float(top.get("score", 0.75)), 3),
        })

    for diag in diagnoses[:2]:
        if diag.get("confidence", 0) < 0.35:
            continue
        sig = diag.get("signature")
        if not sig or any(m.get("signature") == sig for m in mitigations):
            continue
        add({
            "id": f"diagnose:{sig}",
            "kind": "heal",
            "title": f"Address — {diag.get('title', sig)}",
            "error_text": combined_error_snippet(failures, sig),
            "signature": sig,
            "rationale": f"Diagnosis confidence {diag.get('confidence')}.",
            "confidence": float(diag.get("confidence", 0.5)),
        })

    mitigations.sort(key=lambda m: (-m.get("confidence", 0), m.get("kind") != "bridge"))

    combined = "\n---\n".join(
        f.get("error_text", "") for f in failures if f.get("error_text")
    )[:3000]
    file_path = None
    for f in failures:
        for key in ("file_path", "bridge_target", "scan_path"):
            if f.get(key):
                file_path = f[key]
                break
        if file_path:
            break

    if (combined or file_path) and not _only_stale_sudo_failures(failures, sudo_ready=sudo_ready):
        add({
            "id": "route:best",
            "kind": "best_route",
            "title": "Discover and execute the best route (Bridge + pathways + synthesis)",
            "error_text": combined or "bridge retry",
            "file_path": file_path,
            "rationale": "Exhaust ranked Bridge strategies and synthesized pathways until something works.",
            "confidence": 0.93,
            "risk": "medium",
        })
    elif file_path and _only_stale_sudo_failures(failures, sudo_ready=sudo_ready):
        add({
            "id": "route:best",
            "kind": "best_route",
            "title": "Discover and execute the best route (Bridge + pathways + synthesis)",
            "error_text": combined or "bridge retry",
            "file_path": file_path,
            "rationale": "Retry Bridge for the failed binary.",
            "confidence": 0.93,
            "risk": "medium",
        })

    if healing and len(healing.get("pathways") or []) > 1:
        for pathway in healing["pathways"][1:4]:
            add({
                "id": f"pathway:{pathway.get('id')}",
                "kind": "pathway",
                "title": f"Try pathway — {pathway.get('title', pathway.get('id'))}",
                "error_text": combined or combined_error_snippet(failures, healing.get("primary_signature") or ""),
                "pathway_id": pathway.get("id"),
                "rationale": f"Alternate ranked pathway (score {pathway.get('score')}).",
                "confidence": round(float(pathway.get("score", 0.6)), 3),
            })

    return mitigations


def combined_error_snippet(failures: List[Dict[str, Any]], _signature: str) -> str:
    return "\n".join(f.get("error_text", "") for f in failures if f.get("error_text"))[:2000]


def _mitigation_priority(mitigation: Dict[str, Any]) -> int:
    kind = mitigation.get("kind")
    mid = (mitigation.get("id") or "").lower()
    if kind == "prefix_bootstrap":
        return 0
    if kind == "heal" and "sudo" in mid:
        return 1
    if kind == "modernize_apply":
        return 2
    if kind == "fix_permissions":
        return 3
    if kind == "modernize_retry":
        return 4
    if kind == "best_route":
        return 5
    if kind == "bridge":
        return 6
    if kind == "heal":
        return 7
    if kind == "pathway":
        return 8
    return 9


def _consolidate_mitigations(mitigations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Run prerequisite fixes before exhaustive route discovery."""
    if not any(m.get("kind") == "best_route" for m in mitigations):
        return mitigations
    kept: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    for m in mitigations:
        kind = m.get("kind")
        mid = m.get("id")
        if kind == "best_route":
            kept.append(m)
        elif kind in {"modernize_retry", "modernize_apply", "fix_permissions"}:
            kept.append(m)
        elif kind == "heal" and "sudo" in (mid or "").lower():
            kept.append(m)
        elif kind == "bridge" and not any(x.get("kind") == "best_route" for x in kept):
            if mid not in seen_ids:
                kept.append(m)
        seen_ids.add(mid or "")
    kept.sort(key=_mitigation_priority)
    return kept


def apply_mitigations(
    examination: Dict[str, Any],
    *,
    apply: bool = False,
    sudo_password: Optional[str] = None,
    approval_token: Optional[str] = None,
    only_auto: bool = True,
) -> Dict[str, Any]:
    """Execute mitigations from :func:`examine_failures` when policy allows."""
    from alma_bridge.automation.runner import run_automation
    from alma_bridge.operator.brain import _autonomy

    autonomy = _autonomy()
    server_allows = bool(settings.operator_allow_mutations) or bool(approval_token)
    can_mutate = apply and autonomy in ("assisted", "autonomous") and server_allows

    results: List[Dict[str, Any]] = []
    mitigations = _consolidate_mitigations(examination.get("mitigations") or [])

    for m in mitigations:
        if only_auto:
            if not m.get("auto_eligible"):
                skipped = {
                    "mitigation_id": m["id"],
                    "kind": m.get("kind"),
                    "title": m.get("title"),
                    "skipped": True,
                    "reason": "not auto-eligible",
                }
                skipped.update(_mitigation_report(skipped))
                results.append(skipped)
                continue
        else:
            from alma_bridge.operator.brain import _within_risk

            if not _within_risk({"risk": m.get("risk", "medium")}, autonomy):
                skipped = {
                    "mitigation_id": m["id"],
                    "kind": m.get("kind"),
                    "title": m.get("title"),
                    "skipped": True,
                    "reason": "exceeds max risk",
                }
                skipped.update(_mitigation_report(skipped))
                results.append(skipped)
                continue
        if not can_mutate:
            skipped = {
                "mitigation_id": m["id"],
                "kind": m.get("kind"),
                "title": m.get("title"),
                "skipped": True,
                "reason": "policy blocked apply",
            }
            skipped.update(_mitigation_report(skipped))
            results.append(skipped)
            continue

        kind = m.get("kind")
        outcome: Dict[str, Any] = {"mitigation_id": m["id"], "kind": kind, "title": m.get("title")}

        try:
            if kind == "modernize_retry":
                outcome["execution"] = run_automation(
                    apply=True,
                    allow_mutations=bool(settings.operator_allow_mutations),
                    approval_token=approval_token,
                    sudo_password=sudo_password,
                    step_ids=m.get("step_ids"),
                    verify=True,
                )
            elif kind == "modernize_apply":
                from alma_bridge.execution.privileges import prepare_sudo

                sudo_ok, sudo_err = prepare_sudo(requested=True, password=sudo_password)
                if not sudo_ok:
                    outcome["reason"] = sudo_err
                    outcome["success"] = False
                    outcome.update(_mitigation_report(outcome))
                    results.append(outcome)
                    continue
                outcome["execution"] = run_automation(
                    apply=True,
                    allow_mutations=bool(settings.operator_allow_mutations),
                    approval_token=approval_token,
                    sudo_password=sudo_password,
                    verify=True,
                )
            elif kind == "fix_permissions":
                from alma_bridge.execution.binary_access import ensure_binary_executable

                outcome["execution"] = ensure_binary_executable(
                    m["file_path"],
                    sudo_password=sudo_password,
                )
            elif kind == "prefix_bootstrap":
                from alma_bridge.execution.preflight import apply_ml_wine_fix
                from alma_bridge.hardware.prefixes import find_best_prefix

                fp = m.get("file_path")
                prefix = find_best_prefix(fp) if fp else None
                sig = m.get("error_signature") or "dotnet_missing"
                if not prefix or not fp:
                    outcome["reason"] = "no Wine prefix or file path for bootstrap"
                    outcome["success"] = False
                else:
                    fix = apply_ml_wine_fix(sig, prefix, fp)
                    bridge_out = run_automation(
                        file_path=fp,
                        bridge_run=True,
                        bridge_max_attempts=int(settings.operator_bridge_max_attempts),
                        allow_mutations=bool(settings.operator_allow_mutations),
                        sudo_password=sudo_password,
                        verify=False,
                    )
                    outcome["execution"] = {"prefix_fix": fix, "bridge": bridge_out}
            elif kind == "bridge":
                outcome["execution"] = run_automation(
                    file_path=m["file_path"],
                    bridge_run=True,
                    bridge_max_attempts=int(settings.operator_bridge_max_attempts),
                    allow_mutations=bool(settings.operator_allow_mutations),
                    sudo_password=sudo_password,
                    verify=False,
                )
            elif kind == "heal":
                err = m.get("error_text") or ""
                heal_id = (m.get("id") or "").lower()
                if heal_id.endswith("sudo_credentials") or _is_sudo_credential_failure(
                    {"error_text": err}
                ):
                    from alma_bridge.execution.privileges import prepare_sudo

                    sudo_ok, sudo_err = prepare_sudo(
                        requested=True, password=sudo_password
                    )
                    if not sudo_ok:
                        outcome["reason"] = sudo_err
                        outcome["success"] = False
                        outcome.update(_mitigation_report(outcome))
                        results.append(outcome)
                        continue
                    outcome["execution"] = {
                        "success": True,
                        "summary": "Sudo credentials warmed for host remediation.",
                    }
                else:
                    outcome["execution"] = run_autopilot(
                        err,
                        execute=True,
                        allow_mutations=bool(settings.operator_allow_mutations),
                        pathway_id=m.get("pathway_id"),
                        try_all_pathways=bool(settings.operator_try_all_pathways),
                        sudo_password=sudo_password,
                    )
            elif kind == "best_route":
                from alma_bridge.operator.routes import discover_routes, execute_best_routes

                err = (m.get("error_text") or "").strip()
                fp = m.get("file_path")
                if not err and not fp:
                    outcome["reason"] = (
                        "No error output or program path — paste stderr in the box below "
                        "or run a program via Bridge first."
                    )
                    outcome["success"] = False
                    outcome.update(_mitigation_report(outcome))
                    results.append(outcome)
                    continue
                discovery = discover_routes(err or "bridge retry", file_path=fp)
                outcome["execution"] = execute_best_routes(
                    discovery,
                    apply=True,
                    sudo_password=sudo_password,
                    stop_on_success=True,
                )
            elif kind == "pathway":
                err = m.get("error_text") or ""
                outcome["execution"] = run_autopilot(
                    err,
                    execute=True,
                    allow_mutations=bool(settings.operator_allow_mutations),
                    pathway_id=m.get("pathway_id"),
                    try_all_pathways=False,
                    sudo_password=sudo_password,
                )
            else:
                outcome["skipped"] = True
                outcome["reason"] = f"unknown kind {kind}"
        except Exception as exc:  # noqa: BLE001
            outcome["error"] = str(exc)

        outcome["success"] = _mitigation_success(outcome)
        outcome.update(_mitigation_report(outcome))
        results.append(outcome)
        if kind == "best_route" and outcome.get("success"):
            break
        if kind == "prefix_bootstrap" and outcome.get("success"):
            break

    applied = [r for r in results if not r.get("skipped")]
    return {
        "applied": bool(applied) and can_mutate,
        "can_mutate": can_mutate,
        "results": results,
        "success_count": sum(1 for r in results if r.get("success")),
    }


def _mitigation_success(outcome: Dict[str, Any]) -> bool:
    if outcome.get("skipped"):
        return False
    if outcome.get("error"):
        return False
    ex = outcome.get("execution")
    if isinstance(ex, dict):
        if ex.get("prefix_fix"):
            if isinstance(ex.get("bridge"), dict) and ex["bridge"].get("success"):
                return True
            return bool(ex["prefix_fix"].get("actions"))
        if ex.get("winning_route"):
            return True
        if ex.get("ok"):
            return True
        if ex.get("success_count", 0) > 0:
            return True
        if "success" in ex:
            return bool(ex["success"])
        if ex.get("mutations_applied"):
            return True
        remed = ex.get("executed_remediations") or []
        if remed:
            return all(r.get("ok") for r in remed)
    return False


def _mitigation_report(outcome: Dict[str, Any]) -> Dict[str, Any]:
    """Human-readable status + detail for UI and logs."""
    if outcome.get("skipped"):
        return {
            "status": "skipped",
            "detail": outcome.get("reason") or "Not applied — policy or eligibility blocked this step.",
        }
    if outcome.get("error"):
        return {"status": "failed", "detail": str(outcome["error"])}

    if outcome.get("success"):
        ex = outcome.get("execution") if isinstance(outcome.get("execution"), dict) else {}
        detail = (
            ex.get("summary")
            or ex.get("reason")
            or (f"Winning route: {ex['winning_route']}" if ex.get("winning_route") else None)
            or ("Permissions fixed" if ex.get("method") else None)
            or "Completed successfully."
        )
        return {"status": "succeeded", "detail": str(detail)}

    detail = _extract_execution_failure(outcome.get("execution"))
    if outcome.get("reason") and not detail:
        detail = str(outcome["reason"])
    return {
        "status": "failed",
        "detail": detail or "Mitigation ran but did not resolve the failure.",
    }


def _extract_execution_failure(execution: Any) -> str:
    if not isinstance(execution, dict):
        return ""

    if execution.get("reason"):
        return str(execution["reason"])
    if execution.get("stderr"):
        return str(execution["stderr"])[:500]
    if execution.get("summary") and not execution.get("success"):
        return str(execution["summary"])[:500]

    for phase in execution.get("phases") or []:
        if phase.get("ok"):
            continue
        if phase.get("error"):
            return f"{phase.get('phase', 'phase')} failed: {phase['error']}"[:500]
        data = phase.get("data") or {}
        for step in data.get("results") or []:
            if not step.get("ok"):
                stderr = (step.get("stderr") or "").strip()
                sid = step.get("step_id") or "step"
                if stderr:
                    return f"Step {sid} failed: {stderr}"[:500]
                return f"Step {sid} failed."[:500]

    route_results = execution.get("results") or []
    if execution.get("routes_attempted") == 0 and not execution.get("winning_route"):
        return "No routes discovered — add a program path or paste error output from a failed launch."
    for route in reversed(route_results):
        if route.get("success"):
            continue
        if route.get("error"):
            return f"Route {route.get('route_id', '?')}: {route['error']}"[:500]
        bridge = route.get("execution")
        if isinstance(bridge, dict):
            if bridge.get("summary") and not bridge.get("success"):
                return str(bridge["summary"])[:500]
            if bridge.get("prep", {}).get("reason"):
                return str(bridge["prep"]["reason"])[:500]
        if route.get("reason"):
            return str(route["reason"])[:500]

    remed = execution.get("executed_remediations") or []
    for step in remed:
        if not step.get("ok"):
            return (step.get("stderr") or step.get("command") or "Remediation step failed.")[:500]

    return ""
