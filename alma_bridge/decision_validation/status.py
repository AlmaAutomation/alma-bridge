"""Deterministic validation report status reduction."""

from __future__ import annotations

from typing import List, Tuple

from alma_bridge.decision_review.models import Decision, DecisionPlanReview
from alma_bridge.decision_validation.models import (
    PlanValidationStatus,
    ValidationCheck,
    ValidationCheckCategory,
    ValidationCheckSeverity,
)

# Blocking failures in these categories indicate structural / identity invalidity.
_INVALID_CATEGORIES = frozenset(
    {
        ValidationCheckCategory.PLAN_INTEGRITY,
        ValidationCheckCategory.APPLICATION_IDENTITY,
    }
)

# Checks that surface observational uncertainty without blocking feasibility.
_WARNING_STATUS_CODES = frozenset(
    {
        "optional_unknown_environment",
        "contradictory_evidence",
        "campaign_guard_session_path",
    }
)


def compute_has_warnings(checks: List[ValidationCheck]) -> bool:
    """True when warnings are present but feasibility may still be valid."""
    return any(
        check.severity == ValidationCheckSeverity.WARNING
        or check.code in _WARNING_STATUS_CODES
        for check in checks
    )


def aggregate_status(
    *,
    review: DecisionPlanReview,
    checks: List[ValidationCheck],
    approval_stale_flag: bool,
) -> Tuple[PlanValidationStatus, bool]:
    """Reduce checks to (status, has_warnings) using documented precedence."""
    if approval_stale_flag:
        return PlanValidationStatus.STALE, False

    if review.decision != Decision.APPROVED:
        return PlanValidationStatus.INVALID, False

    blocking_failed = [
        check
        for check in checks
        if not check.passed and check.severity == ValidationCheckSeverity.BLOCKING
    ]
    if blocking_failed:
        if any(check.category in _INVALID_CATEGORIES for check in blocking_failed):
            return PlanValidationStatus.INVALID, False
        return PlanValidationStatus.BLOCKED, False

    if any(check.code == "required_unknown_environment" for check in checks):
        return PlanValidationStatus.INDETERMINATE, False

    has_warnings = compute_has_warnings(checks)
    return PlanValidationStatus.VALID, has_warnings
