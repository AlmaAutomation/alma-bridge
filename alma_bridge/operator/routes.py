"""Unified route discovery — Bridge strategies + autopilot pathways + synthesis."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from alma_bridge.compliance.learning import record_pathway_outcome
from alma_bridge.config import settings
from alma_bridge.hardware.prefixes import find_best_prefix
from alma_bridge.learning.remediation_learning import record_remediation_outcome
from alma_bridge.session.services.routes import (
    DefaultRouteExecutionService,
    RouteDiscoveryService,
    RouteExecutionContext,
    RouteSelectionService,
)

_route_discovery = RouteDiscoveryService()
_route_selection = RouteSelectionService()
_route_executor = DefaultRouteExecutionService()


def discover_routes(
    error_text: str,
    *,
    file_path: Optional[str] = None,
    failures: Optional[List[Dict[str, Any]]] = None,
    os_release: Optional[str] = None,
) -> Dict[str, Any]:
    """Rank every viable route: host pathways + Bridge execution strategies."""
    return _route_discovery.discover(
        error_text,
        file_path=file_path,
        failures=failures,
        os_release=os_release,
    )


def _record_route_learning(
    route: Dict[str, Any],
    discovery: Dict[str, Any],
    *,
    success: bool,
    bridge_out: Optional[Dict[str, Any]] = None,
) -> None:
    sig = (
        route.get("signature")
        or route.get("bridge_signature")
        or discovery.get("bridge_signature")
        or discovery.get("primary_signature")
        or "unknown_error"
    )
    pathway_id = route.get("pathway_id")
    if pathway_id:
        try:
            record_pathway_outcome(sig, pathway_id, success)
        except Exception:  # noqa: BLE001
            pass
    rem_id = None
    if bridge_out:
        rem_id = bridge_out.get("winning_remediation")
    if not rem_id:
        rem_id = route.get("preferred_remediation_id") or discovery.get("preferred_remediation_id")
    if rem_id:
        try:
            record_remediation_outcome(sig, rem_id, success)
        except Exception:  # noqa: BLE001
            pass


def execute_best_routes(
    discovery: Dict[str, Any],
    *,
    apply: bool = False,
    sudo_password: Optional[str] = None,
    max_routes: Optional[int] = None,
    stop_on_success: bool = True,
    allow_mutations: Optional[bool] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute ranked routes via RouteExecutionService (no BridgeOrchestrator).

    Bridge retry routes return ``requires_bridge_retry`` — callers must resume an
    existing session through BridgeOrchestrator, not spawn a new root session.
    """
    routes = _route_selection.select(
        discovery,
        budget=max_routes or int(settings.operator_max_route_attempts),
    )
    if not routes:
        return {"applied": False, "results": [], "success_count": 0, "winning_route": None}

    mutations = (
        bool(allow_mutations)
        if allow_mutations is not None
        else bool(settings.operator_allow_mutations)
    )
    results: List[Dict[str, Any]] = []
    winning: Optional[str] = None
    fp = discovery.get("file_path") or ""
    ctx = RouteExecutionContext(
        session_id=session_id or "operator-route-exec",
        correlation_id=session_id or "operator-route-exec",
        file_path=fp,
        wine_prefix=find_best_prefix(fp) if fp else None,
        error_text=discovery.get("error_text") or "",
        bridge_signature=discovery.get("bridge_signature"),
        preferred_remediation_id=discovery.get("preferred_remediation_id"),
        sudo_password=sudo_password,
        auto_remediate=settings.bridge_auto_remediate,
    )

    for route in routes:
        kind = route.get("kind")
        outcome: Dict[str, Any] = {
            "route_id": route["id"],
            "kind": kind,
            "title": route.get("title"),
        }

        if not apply:
            outcome["skipped"] = True
            outcome["reason"] = "dry-run"
            results.append(outcome)
            continue

        try:
            execution = _route_executor.execute_route(
                route,
                discovery,
                ctx,
                apply=True,
                allow_host_mutations=mutations,
            )
            outcome["execution"] = {
                "summary": execution.summary,
                "prefix_fix": execution.prefix_fix,
                "heal": execution.heal,
                "requires_bridge_retry": execution.requires_bridge_retry,
                "preferred_strategy_id": execution.preferred_strategy_id,
                "preferred_remediation_id": execution.preferred_remediation_id,
            }
            if execution.requires_bridge_retry:
                outcome["requires_bridge_retry"] = True
                outcome["success"] = False
            else:
                outcome["success"] = execution.success
        except Exception as exc:  # noqa: BLE001
            outcome["error"] = str(exc)
            outcome["success"] = False

        if "success" not in outcome:
            outcome["success"] = _route_success(outcome, require_binary=bool(discovery.get("file_path")))

        _record_route_learning(
            route,
            discovery,
            success=bool(outcome.get("success")),
            bridge_out=None,
        )
        results.append(outcome)
        if outcome.get("success"):
            winning = route["id"]
            if stop_on_success:
                break

    return {
        "applied": apply,
        "results": results,
        "success_count": sum(1 for r in results if r.get("success")),
        "winning_route": winning,
        "routes_attempted": len([r for r in results if not r.get("skipped")]),
        "bridge_signature": discovery.get("bridge_signature"),
        "preferred_remediation_id": discovery.get("preferred_remediation_id"),
        "requires_orchestrator_resume": any(r.get("requires_bridge_retry") for r in results),
    }


def _extract_bridge_outcome(outcome: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ex = outcome.get("execution")
    if not isinstance(ex, dict):
        return None
    if ex.get("success") is not None and "bridge" not in ex:
        return ex
    bridge = ex.get("bridge")
    return bridge if isinstance(bridge, dict) else None


def _route_success(outcome: Dict[str, Any], *, require_binary: bool) -> bool:
    if outcome.get("skipped") or outcome.get("error"):
        return False
    if outcome.get("requires_bridge_retry"):
        return False
    ex = outcome.get("execution")
    if not isinstance(ex, dict):
        return False

    if ex.get("prefix_fix"):
        if require_binary and ex.get("requires_bridge_retry"):
            return False
        return bool(ex["prefix_fix"].get("actions"))

    heal = ex.get("heal")
    if heal is not None:
        if require_binary:
            return False
        if isinstance(heal, dict):
            return bool(heal.get("success"))

    if "success" in ex:
        return bool(ex["success"])
    return False
