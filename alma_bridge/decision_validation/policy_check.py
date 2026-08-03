"""Policy feasibility simulation without mutation authority."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.config import settings
from alma_bridge.decision.models import DecisionPlan
from alma_bridge.decision_review.models import Decision, DecisionPlanReview
from alma_bridge.decision_validation.models import (
    ValidationCheck,
    ValidationCheckCategory,
    ValidationCheckSeverity,
)
from alma_bridge.schemas.models import BridgeRequest
from alma_bridge.storage import outcomes
from alma_bridge.validation.campaign_guard import (
    CampaignPrefixRejected,
    validate_campaign_bridge_request,
)


def _check(
    *,
    code: str,
    message: str,
    passed: bool,
    severity: ValidationCheckSeverity = ValidationCheckSeverity.BLOCKING,
) -> ValidationCheck:
    return ValidationCheck(
        check_id=sha256_v1({"category": "policy_feasibility", "code": code}),
        category=ValidationCheckCategory.POLICY_FEASIBILITY,
        code=code,
        message=message,
        severity=severity,
        passed=passed,
    )


def simulate_policy_feasibility(
    plan: DecisionPlan,
    review: DecisionPlanReview,
) -> List[ValidationCheck]:
    """Simulate PolicyGate and campaign guards without performing mutations."""
    checks: List[ValidationCheck] = []

    checks.append(
        _check(
            code="approval_not_mutation_authority",
            message=(
                "Human approval is recorded but does not grant mutation authority."
                if review.decision == Decision.APPROVED
                else "Review decision is not an approval; mutation authority remains absent."
            ),
            passed=True,
            severity=ValidationCheckSeverity.INFO,
        )
    )

    auto_remediate_enabled = bool(settings.operator_allow_mutations)
    prefix_mutation_allowed = auto_remediate_enabled
    checks.append(
        _check(
            code="prefix_mutation_policy_simulation",
            message=(
                "Policy simulation: prefix mutation would be denied (dry-run only)."
                if not prefix_mutation_allowed
                else "Policy simulation: prefix mutation preconditions exist but dry-run performs none."
            ),
            passed=not prefix_mutation_allowed,
            severity=ValidationCheckSeverity.INFO if prefix_mutation_allowed else ValidationCheckSeverity.WARNING,
        )
    )

    campaign_check = _simulate_campaign_guard(plan)
    if campaign_check is not None:
        checks.append(campaign_check)

    return checks


def _simulate_campaign_guard(plan: DecisionPlan) -> Optional[ValidationCheck]:
    if not settings.validation_campaign_mode:
        return None

    file_path = _session_file_path(plan.session_id)
    if not file_path:
        return _check(
            code="campaign_guard_session_path",
            message="Campaign guard active but session executable path is unavailable for simulation.",
            passed=False,
            severity=ValidationCheckSeverity.WARNING,
        )

    prefix = _session_wine_prefix(plan.session_id)
    request = BridgeRequest(file_path=file_path, wine_prefix=prefix, runtime_hint="wine")
    try:
        validate_campaign_bridge_request(request)
        return _check(
            code="campaign_guard_passed",
            message="Campaign guard simulation passed without execution.",
            passed=True,
            severity=ValidationCheckSeverity.INFO,
        )
    except CampaignPrefixRejected as exc:
        return _check(
            code="campaign_guard_violation",
            message=f"Campaign guard would reject this plan: {exc}",
            passed=False,
            severity=ValidationCheckSeverity.WARNING,
        )


def _session_file_path(session_id: Optional[str]) -> Optional[str]:
    if not session_id:
        return None
    session = outcomes.get_session(session_id)
    if not session:
        return None
    path = session.get("file_path")
    return str(path) if path else None


def _session_wine_prefix(session_id: Optional[str]) -> Optional[str]:
    if not session_id:
        return None
    session = outcomes.get_session(session_id)
    if not session:
        return None
    attempts = session.get("attempts") or []
    if not attempts:
        return None
    env = attempts[-1].get("env") or {}
    prefix = env.get("WINEPREFIX")
    return str(prefix) if prefix else None
