"""Alma AI Operator — the decision brain.

Observes system + ML state, decides which modernization / self-healing actions
to take, scores each by confidence and risk, and (when authorized) executes them
through the existing automation spine. This is the "AI that sees the systems and
the ML and applies the bridging/fixing/modernization" layer.

Safety model
------------
The brain never mutates a host on its own. Real changes only happen when a caller
explicitly asks to apply AND the server policy permits it (autonomy level +
``operator_allow_mutations``). Everything else is a plan/dry-run.
"""

from __future__ import annotations

import platform
import socket
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from alma_bridge.automation.runner import machine_health, run_automation
from alma_bridge.automation.sessions import list_automation_sessions
from alma_bridge.compliance.autopilot import diagnose, host_summary, plan_pathways
from alma_bridge.compliance.learning import pathway_scores
from alma_bridge.compliance.modernization import assess_host, build_modernization_playbook
from alma_bridge.config import settings
from alma_bridge.learning.ranker import ranker_status
from alma_bridge.operator.failures import apply_mitigations, examine_failures

# Autonomy levels, ordered least → most capable.
AUTONOMY_LEVELS = ("observe", "recommend", "assisted", "autonomous")
RISK_ORDER = {"low": 0, "medium": 1, "high": 2}

# Step-id / command keywords → risk class. Anything unmatched defaults to medium.
_LOW_RISK_HINTS = (
    "advisory",
    "checklist",
    "shortcut",
    "swappiness",
    "zram",
    "sysctl",
    "refresh",
    "ldconfig",
    "note",
    "recommend",
    "profile",
)
_HIGH_RISK_HINTS = ("purge", "remove", "rm ", "dd ", "mkfs", "format", "wipe", "delete")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _autonomy() -> str:
    level = (settings.operator_autonomy or "observe").strip().lower()
    return level if level in AUTONOMY_LEVELS else "observe"


def _max_risk_level(autonomy: str) -> int:
    max_risk = RISK_ORDER.get((settings.operator_max_risk or "low").lower(), 0)
    if autonomy == "assisted":
        max_risk = min(max_risk, RISK_ORDER["low"])
    return max_risk


def _within_risk(action: Dict[str, Any], autonomy: str) -> bool:
    return RISK_ORDER.get(action.get("risk", "medium"), 2) <= _max_risk_level(autonomy)


def _apply_all_mode(autonomy: str) -> bool:
    """Full troubleshoot-and-fix: apply every action within max_risk."""
    return (
        autonomy == "autonomous"
        and bool(settings.operator_apply_all)
        and bool(settings.operator_allow_mutations)
    )


def _classify_risk(step: Dict[str, Any]) -> str:
    text = f"{step.get('id', '')} {step.get('command', '')} {step.get('kind', '')}".lower()
    if any(h in text for h in _HIGH_RISK_HINTS):
        return "high"
    if any(h in text for h in _LOW_RISK_HINTS):
        return "low"
    if step.get("kind") == "diagnostic":
        return "low"
    return "medium"


def _step_confidence(step: Dict[str, Any], *, verdict: Optional[str], learned: float | None) -> float:
    """Blend a heuristic prior with any learned success rate for this action."""
    base = 0.62
    if step.get("kind") == "diagnostic":
        base = 0.9
    if verdict == "critical_legacy_os":
        base -= 0.12
    elif verdict == "ready":
        base += 0.08
    if learned is not None:
        # Weight learned evidence in as we accumulate it.
        base = 0.5 * base + 0.5 * learned
    return round(max(0.05, min(0.99, base)), 3)


def _eligible(action: Dict[str, Any], autonomy: str) -> bool:
    """Would policy let this action be auto-applied?"""
    if autonomy in ("observe", "recommend"):
        return False
    if not _within_risk(action, autonomy):
        return False
    return action["confidence"] >= float(settings.operator_min_confidence)


def observe(
    *,
    os_release: Optional[str] = None,
    error_text: Optional[str] = None,
    examine_failures_limit: int = 10,
) -> Dict[str, Any]:
    """Snapshot of everything the operator can 'see': host, gaps, ML, history, failures."""
    assessment = assess_host(os_release=os_release)
    playbook = build_modernization_playbook(assessment, os_release=os_release)
    sessions = list_automation_sessions(limit=5)
    ranker = ranker_status()
    failure_examination = examine_failures(limit=examine_failures_limit)

    merged_error = error_text or failure_examination.get("combined_error_text")
    healing: Optional[Dict[str, Any]] = None
    route_discovery: Optional[Dict[str, Any]] = None
    if merged_error or failure_examination.get("failures"):
        from alma_bridge.operator.routes import discover_routes

        route_discovery = discover_routes(
            merged_error or "",
            failures=failure_examination.get("failures"),
            os_release=os_release,
        )
    if merged_error:
        healing = plan_pathways(merged_error, os_release=os_release)

    return {
        "observed_at": _now(),
        "hostname": socket.gethostname(),
        "machine": platform.machine(),
        "host": host_summary(),
        "verdict": assessment.get("verdict"),
        "lab_readiness_score": assessment.get("potato_score"),
        "gaps": assessment.get("gaps", []),
        "summary": assessment.get("summary"),
        "package_manager": assessment.get("package_manager"),
        "ml": {
            "ranker_loaded": bool(ranker.get("model_loaded")),
            "metadata": ranker.get("metadata"),
        },
        "recent_sessions": sessions,
        "failure_examination": {
            k: v
            for k, v in failure_examination.items()
            if k != "healing"
        },
        "route_discovery": {
            k: v for k, v in (route_discovery or {}).items() if k != "routes"
        } | {
            "top_routes": [
                {
                    "id": r.get("id"),
                    "kind": r.get("kind"),
                    "title": r.get("title"),
                    "score": r.get("score"),
                    "signature": r.get("signature") or r.get("bridge_signature"),
                }
                for r in ((route_discovery or {}).get("routes") or [])[:8]
            ],
        } if route_discovery else None,
        "healing": healing,
        "_assessment": assessment,
        "_playbook": playbook,
        "_failure_examination_full": failure_examination,
        "_route_discovery_full": route_discovery,
    }


def decide(observation: Dict[str, Any]) -> Dict[str, Any]:
    """Turn an observation into a ranked, risk-scored action plan."""
    autonomy = _autonomy()
    playbook = observation.get("_playbook") or {}
    verdict = observation.get("verdict")
    steps = playbook.get("steps", [])
    apply_ids = set(playbook.get("apply_step_ids", []))

    # Learned success signal from the self-healing store, if we have a signature.
    learned_rate: float | None = None
    healing = observation.get("healing")
    healing_signature = healing.get("primary_signature") if healing else None
    if healing_signature:
        scores = pathway_scores(healing_signature)
        if scores:
            learned_rate = max(s["rate"] for s in scores.values())

    actions: List[Dict[str, Any]] = []
    for step in steps:
        if step["id"] not in apply_ids:
            continue
        risk = _classify_risk(step)
        confidence = _step_confidence(step, verdict=verdict, learned=learned_rate)
        action = {
            "id": step["id"],
            "title": step.get("description", step["id"]),
            "kind": "modernize",
            "risk": risk,
            "confidence": confidence,
            "requires_sudo": step.get("kind") == "remediation",
            "rationale": _rationale_for(step, observation),
        }
        action["auto_eligible"] = _eligible(action, autonomy)
        actions.append(action)

    # Self-healing action when an error signature is present.
    if healing and healing.get("pathways"):
        top = healing["pathways"][0]
        diagnoses = healing.get("diagnoses") or [{}]
        diag_confidence = diagnoses[0].get("confidence")
        heal_conf = round(float(top.get("score", 0.5)), 3)
        heal_action = {
            "id": f"heal:{top.get('id', 'pathway')}",
            "title": f"Self-heal — {top.get('title', 'apply top pathway')}",
            "kind": "heal",
            "risk": "medium",
            "confidence": heal_conf,
            "requires_sudo": True,
            "rationale": (
                f"Diagnosed '{healing_signature}' "
                f"(confidence {diag_confidence}); "
                f"{len(healing['pathways'])} candidate pathway(s)."
            ),
        }
        heal_action["auto_eligible"] = _eligible(heal_action, autonomy)
        actions.append(heal_action)

    # ML upkeep: flag when the ranker has never been trained.
    ml_actions: List[Dict[str, Any]] = []
    if not observation.get("ml", {}).get("ranker_loaded"):
        ml_actions.append({
            "id": "ml:train_ranker",
            "title": "Train strategy ranker from accumulated bridge outcomes",
            "kind": "ml",
            "risk": "low",
            "confidence": 0.8,
            "requires_sudo": False,
            "auto_eligible": False,
            "rationale": "No ML model loaded yet; ranker will improve strategy selection once trained.",
        })

    actions.sort(key=lambda a: (RISK_ORDER.get(a["risk"], 2), -a["confidence"]))
    auto_ids = [a["id"] for a in actions if a["auto_eligible"] and a["kind"] == "modernize"]
    apply_all = _apply_all_mode(autonomy)
    if apply_all:
        apply_step_ids = [
            a["id"] for a in actions if a.get("kind") == "modernize" and _within_risk(a, autonomy)
        ]
    else:
        apply_step_ids = list(auto_ids)

    # Failure-driven mitigations (Bridge retry, step retry, self-heal).
    failure_exam = observation.get("_failure_examination_full") or {}
    mitigations = failure_exam.get("mitigations") or []
    failure_actions: List[Dict[str, Any]] = []
    for m in mitigations:
        failure_actions.append({
            "id": m["id"],
            "title": m.get("title", m["id"]),
            "kind": m.get("kind", "mitigation"),
            "risk": m.get("risk", "medium"),
            "confidence": m.get("confidence", 0.75),
            "requires_sudo": m.get("kind") in ("modernize_retry", "heal"),
            "rationale": m.get("rationale", ""),
            "auto_eligible": m.get("auto_eligible", False),
            "mitigation": m,
        })
    # Prioritize failure fixes ahead of generic baseline steps.
    actions = failure_actions + actions

    return {
        "planned_at": _now(),
        "autonomy": autonomy,
        "policy": {
            "allow_mutations": bool(settings.operator_allow_mutations),
            "max_risk": settings.operator_max_risk,
            "min_confidence": settings.operator_min_confidence,
            "apply_all": apply_all,
        },
        "verdict": verdict,
        "lab_readiness_score": observation.get("lab_readiness_score"),
        "failure_count": failure_exam.get("failure_count", 0),
        "actions": actions,
        "ml_actions": ml_actions,
        "auto_apply_step_ids": auto_ids,
        "apply_step_ids": apply_step_ids,
        "auto_mitigation_count": sum(1 for a in failure_actions if a.get("auto_eligible")),
        "mitigation_apply_count": sum(
            1
            for m in mitigations
            if _within_risk({"risk": m.get("risk", "medium")}, autonomy)
        ) if apply_all else sum(1 for a in failure_actions if a.get("auto_eligible")),
        "recommendation": _recommendation(verdict, actions, autonomy, failure_exam, apply_all),
    }


def _rationale_for(step: Dict[str, Any], observation: Dict[str, Any]) -> str:
    gaps = observation.get("gaps", [])
    if gaps:
        return f"Closes lab-readiness gap(s): {', '.join(gaps[:3])}."
    return "Part of the recommended modernization baseline for this host."


def _recommendation(
    verdict: Optional[str],
    actions: List[Dict[str, Any]],
    autonomy: str,
    failure_exam: Optional[Dict[str, Any]] = None,
    apply_all: bool = False,
) -> str:
    failure_exam = failure_exam or {}
    fc = failure_exam.get("failure_count", 0)
    auto_mit = failure_exam.get("auto_mitigation_count", 0)
    mit_apply = failure_exam.get("mitigations") or []
    mit_within_risk = sum(
        1 for m in mit_apply if _within_risk({"risk": m.get("risk", "medium")}, autonomy)
    )

    if fc:
        base = f"Examined {fc} failed attempt(s)."
        if apply_all and autonomy == "autonomous" and settings.operator_allow_mutations:
            return (
                f"{base} Full auto mode — will apply all {mit_within_risk} mitigation(s) within "
                f"{settings.operator_max_risk} risk (Bridge retry, step retry, self-heal)."
            )
        if auto_mit and autonomy in ("assisted", "autonomous") and settings.operator_allow_mutations:
            return f"{base} {auto_mit} mitigation(s) ready to auto-apply (Bridge retry, step retry, self-heal)."
        if auto_mit:
            return f"{base} {auto_mit} mitigation(s) planned — enable mutations to apply."
        return f"{base} Review mitigations below."

    remediations = [a for a in actions if a["kind"] == "modernize"]
    if not remediations:
        return "Host is already at baseline — no modernization actions required."
    if apply_all and autonomy == "autonomous" and settings.operator_allow_mutations:
        within = [a for a in remediations if _within_risk(a, autonomy)]
        return (
            f"Full auto mode — operator will troubleshoot and apply all {len(within)} "
            f"modernization step(s) within {settings.operator_max_risk} risk."
        )
    eligible = [a for a in remediations if a["auto_eligible"]]
    if autonomy in ("observe", "recommend"):
        return (
            f"{len(remediations)} action(s) recommended. Autonomy is '{autonomy}', so the "
            "operator will not apply changes — review and run manually or raise autonomy."
        )
    if not settings.operator_allow_mutations:
        return (
            f"{len(eligible)} action(s) are policy-eligible, but operator_allow_mutations is off. "
            "Enable it to let the operator apply changes."
        )
    return f"Operator can auto-apply {len(eligible)} of {len(remediations)} action(s) within risk budget."


def run_cycle(
    *,
    apply: bool = False,
    os_release: Optional[str] = None,
    error_text: Optional[str] = None,
    sudo_password: Optional[str] = None,
    approval_token: Optional[str] = None,
    trigger: str = "manual",
) -> Dict[str, Any]:
    """One full observe → decide → (optionally) execute cycle.

    Real mutations require: apply=True AND autonomy in {assisted, autonomous}
    AND settings.operator_allow_mutations (or a valid approval_token).

    In autonomous + operator_apply_all mode, every mitigation and modernization
    step within max_risk is executed — full troubleshoot-and-fix.
    """
    from alma_bridge.compliance.autopilot import run_autopilot

    observation = observe(os_release=os_release, error_text=error_text)
    plan = decide(observation)
    autonomy = plan["autonomy"]
    failure_exam = observation.get("_failure_examination_full") or {}
    apply_all = _apply_all_mode(autonomy)

    step_ids = plan.get("apply_step_ids") or plan["auto_apply_step_ids"]
    server_allows = bool(settings.operator_allow_mutations) or bool(approval_token)
    will_apply = bool(
        apply
        and autonomy in ("assisted", "autonomous")
        and server_allows
    )

    remediation: Optional[Dict[str, Any]] = None
    execution: Optional[Dict[str, Any]] = None
    healing_executions: List[Dict[str, Any]] = []

    if will_apply and failure_exam.get("mitigations"):
        remediation = apply_mitigations(
            failure_exam,
            apply=True,
            sudo_password=sudo_password,
            approval_token=approval_token,
            only_auto=not apply_all,
        )

    heal_error = error_text or failure_exam.get("combined_error_text") or ""
    if will_apply and heal_error:
        for action in plan.get("actions", []):
            if action.get("kind") != "heal":
                continue
            if apply_all:
                if not _within_risk(action, autonomy):
                    continue
            elif not action.get("auto_eligible"):
                continue
            try:
                healing_executions.append({
                    "action_id": action["id"],
                    "title": action.get("title"),
                    "execution": run_autopilot(
                        heal_error,
                        execute=True,
                        allow_mutations=bool(settings.operator_allow_mutations),
                        sudo_password=sudo_password,
                    ),
                })
            except Exception as exc:  # noqa: BLE001
                healing_executions.append({
                    "action_id": action["id"],
                    "title": action.get("title"),
                    "error": str(exc),
                })

    if will_apply and step_ids:
        execution = run_automation(
            playbook_recipe=None,
            apply=True,
            allow_mutations=bool(settings.operator_allow_mutations),
            approval_token=approval_token,
            sudo_password=sudo_password,
            step_ids=step_ids,
            verify=True,
            error_text=heal_error or None,
            os_release=os_release,
        )

    return {
        "cycle_at": _now(),
        "trigger": trigger,
        "applied": will_apply,
        "apply_all": apply_all,
        "applied_step_ids": step_ids if will_apply else [],
        "remediation": remediation,
        "healing_executions": healing_executions or None,
        "observation": {
            k: v for k, v in observation.items() if not k.startswith("_")
        },
        "plan": plan,
        "execution": execution,
    }
