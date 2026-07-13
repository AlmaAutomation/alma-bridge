from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Literal, Optional

from alma_bridge.config import settings


class MutationScope(str, Enum):
    WINE_PREFIX = "wine_prefix"
    HOST_PACKAGES = "host_packages"
    HOST_CONFIG = "host_config"
    HOST_FILES = "host_files"
    ENVIRONMENT = "environment"
    WRAPPERS = "wrappers"
    SERVICES = "services"
    CONTAINER = "container"
    READ_ONLY = "read_only"


class ActionType(str, Enum):
    REMEDIATION = "remediation"
    PREFLIGHT = "preflight"
    ROUTE = "route"
    EXECUTION = "execution"
    ESCALATION = "escalation"
    INSPECT = "inspect"


class ExecutionScope(str, Enum):
    BRIDGE_SESSION = "bridge_session"
    OPERATOR = "operator"
    AUTOMATION = "automation"
    API = "api"


RiskLevel = Literal["low", "medium", "high"]


@dataclass
class ActionIntent:
    action_id: str
    action_type: ActionType
    mutation_scope: MutationScope
    execution_scope: ExecutionScope
    risk: RiskLevel
    actor: str
    session_id: str
    correlation_id: str
    target_resource: str = ""
    prefix_key: Optional[str] = None
    rollback_available: bool = False
    requested_autonomy: Optional[str] = None
    approval_context: Optional[Dict[str, Any]] = None
    protocol_id: Optional[str] = None
    remediation_id: Optional[str] = None
    route_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    auto_remediate_requested: Optional[bool] = None


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str
    risk: RiskLevel
    approval_required: bool
    scope: MutationScope
    rollback_required: bool
    concurrency_key: Optional[str]
    audit: Dict[str, Any] = field(default_factory=dict)


class PolicyGate:
    """Deterministic mutation policy for Bridge execution paths."""

    def evaluate(self, intent: ActionIntent) -> PolicyDecision:
        audit = {
            "action_id": intent.action_id,
            "action_type": intent.action_type.value,
            "session_id": intent.session_id,
            "correlation_id": intent.correlation_id,
            "actor": intent.actor,
        }

        if intent.mutation_scope == MutationScope.READ_ONLY:
            return PolicyDecision(
                allowed=True,
                reason="read_only",
                risk="low",
                approval_required=False,
                scope=intent.mutation_scope,
                rollback_required=False,
                concurrency_key=None,
                audit=audit,
            )

        auto_ok = self._auto_remediate_allowed(intent)
        host_ok = bool(settings.operator_allow_mutations)

        if intent.mutation_scope == MutationScope.WINE_PREFIX:
            if not auto_ok:
                return PolicyDecision(
                    allowed=False,
                    reason="wine_prefix_mutation_blocked:auto_remediate_disabled",
                    risk=intent.risk,
                    approval_required=True,
                    scope=intent.mutation_scope,
                    rollback_required=intent.rollback_available,
                    concurrency_key=intent.prefix_key,
                    audit=audit,
                )
            return PolicyDecision(
                allowed=True,
                reason="wine_prefix_mutation_allowed",
                risk=intent.risk,
                approval_required=False,
                scope=intent.mutation_scope,
                rollback_required=intent.rollback_available,
                concurrency_key=intent.prefix_key,
                audit=audit,
            )

        if intent.mutation_scope in {
            MutationScope.HOST_PACKAGES,
            MutationScope.HOST_CONFIG,
            MutationScope.HOST_FILES,
            MutationScope.SERVICES,
        }:
            if not host_ok:
                return PolicyDecision(
                    allowed=False,
                    reason="host_mutation_blocked:operator_allow_mutations_disabled",
                    risk=intent.risk,
                    approval_required=True,
                    scope=intent.mutation_scope,
                    rollback_required=True,
                    concurrency_key=intent.prefix_key,
                    audit=audit,
                )
            if not self._within_risk(intent.risk):
                return PolicyDecision(
                    allowed=False,
                    reason=f"host_mutation_blocked:risk_{intent.risk}_exceeds_max",
                    risk=intent.risk,
                    approval_required=True,
                    scope=intent.mutation_scope,
                    rollback_required=True,
                    concurrency_key=intent.prefix_key,
                    audit=audit,
                )

        if intent.action_type == ActionType.EXECUTION:
            return PolicyDecision(
                allowed=True,
                reason="execution_allowed",
                risk="low",
                approval_required=False,
                scope=MutationScope.READ_ONLY,
                rollback_required=False,
                concurrency_key=None,
                audit=audit,
            )

        if intent.mutation_scope in {MutationScope.ENVIRONMENT, MutationScope.WRAPPERS, MutationScope.CONTAINER}:
            if not auto_ok and intent.mutation_scope != MutationScope.CONTAINER:
                return PolicyDecision(
                    allowed=False,
                    reason="mutation_blocked:auto_remediate_disabled",
                    risk=intent.risk,
                    approval_required=True,
                    scope=intent.mutation_scope,
                    rollback_required=False,
                    concurrency_key=intent.prefix_key,
                    audit=audit,
                )

        return PolicyDecision(
            allowed=True,
            reason="mutation_allowed",
            risk=intent.risk,
            approval_required=False,
            scope=intent.mutation_scope,
            rollback_required=intent.rollback_available,
            concurrency_key=intent.prefix_key,
            audit=audit,
        )

    def _auto_remediate_allowed(self, intent: ActionIntent) -> bool:
        if intent.auto_remediate_requested is not None:
            return bool(intent.auto_remediate_requested)
        return bool(settings.bridge_auto_remediate)

    def _within_risk(self, risk: RiskLevel) -> bool:
        order = {"low": 0, "medium": 1, "high": 2}
        max_risk = (settings.operator_max_risk or "low").lower()
        return order.get(risk, 2) <= order.get(max_risk, 0)
