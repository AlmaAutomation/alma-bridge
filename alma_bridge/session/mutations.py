from __future__ import annotations

from typing import Any, Callable, Dict, Optional, TypeVar

from alma_bridge.session.policy import (
    ActionIntent,
    ActionType,
    ExecutionScope,
    MutationScope,
    PolicyGate,
    PolicyDecision,
)
from alma_bridge.session.prefix_lock import normalize_prefix_key, prefix_lock

T = TypeVar("T")


def build_preflight_intent(
    *,
    action_id: str,
    session_id: str,
    correlation_id: str,
    wine_prefix: str,
    auto_remediate: Optional[bool] = None,
    risk: str = "medium",
) -> ActionIntent:
    return ActionIntent(
        action_id=action_id,
        action_type=ActionType.PREFLIGHT,
        mutation_scope=MutationScope.WINE_PREFIX,
        execution_scope=ExecutionScope.BRIDGE_SESSION,
        risk=risk,  # type: ignore[arg-type]
        actor="bridge_orchestrator",
        session_id=session_id,
        correlation_id=correlation_id,
        target_resource=wine_prefix,
        prefix_key=normalize_prefix_key(wine_prefix),
        rollback_available=False,
        auto_remediate_requested=auto_remediate,
    )


def build_route_intent(
    *,
    route: Dict[str, Any],
    session_id: str,
    correlation_id: str,
    auto_remediate: Optional[bool] = None,
) -> ActionIntent:
    kind = route.get("kind", "route")
    scope = MutationScope.WINE_PREFIX
    if kind == "pathway":
        scope = MutationScope.HOST_PACKAGES
    return ActionIntent(
        action_id=str(route.get("id") or "route"),
        action_type=ActionType.ROUTE,
        mutation_scope=scope,
        execution_scope=ExecutionScope.BRIDGE_SESSION,
        risk="medium",
        actor="bridge_orchestrator",
        session_id=session_id,
        correlation_id=correlation_id,
        target_resource=str(route.get("file_path") or ""),
        route_id=str(route.get("id") or ""),
        auto_remediate_requested=auto_remediate,
        metadata={"route_kind": kind},
    )


def build_remediation_intent(
    *,
    remediation: Dict[str, Any],
    session_id: str,
    correlation_id: str,
    wine_prefix: str,
    auto_remediate: Optional[bool] = None,
) -> ActionIntent:
    return ActionIntent(
        action_id=str(remediation.get("id") or "baseline"),
        action_type=ActionType.REMEDIATION,
        mutation_scope=MutationScope.WINE_PREFIX,
        execution_scope=ExecutionScope.BRIDGE_SESSION,
        risk="medium",
        actor="bridge_orchestrator",
        session_id=session_id,
        correlation_id=correlation_id,
        target_resource=wine_prefix,
        prefix_key=normalize_prefix_key(wine_prefix),
        remediation_id=str(remediation.get("id") or ""),
        auto_remediate_requested=auto_remediate,
    )


def evaluate_or_block(
    intent: ActionIntent,
    policy: PolicyGate,
) -> PolicyDecision:
    return policy.evaluate(intent)


def run_prefix_mutation(
    intent: ActionIntent,
    policy: PolicyGate,
    fn: Callable[[], T],
    *,
    lock_timeout_sec: Optional[float] = None,
) -> tuple[Optional[PolicyDecision], Optional[T], Optional[str]]:
    """Evaluate policy, acquire prefix lock, run mutation. Returns (decision, result, error)."""
    decision = policy.evaluate(intent)
    if not decision.allowed:
        return decision, None, decision.reason
    if not intent.prefix_key:
        try:
            return decision, fn(), None
        except Exception as exc:  # noqa: BLE001
            return decision, None, str(exc)
    try:
        with prefix_lock(
            intent.prefix_key,
            session_id=intent.session_id,
            timeout_sec=lock_timeout_sec,
            owner=intent.actor,
        ):
            return decision, fn(), None
    except Exception as exc:  # noqa: BLE001
        return decision, None, str(exc)
