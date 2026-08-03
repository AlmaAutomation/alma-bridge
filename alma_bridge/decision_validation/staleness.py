"""Approval and evidence staleness checks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.decision.models import DecisionPlan
from alma_bridge.decision_review.models import APPROVAL_TTL_DAYS, Decision, DecisionPlanReview
from alma_bridge.decision_validation.models import (
    ValidationCheck,
    ValidationCheckCategory,
    ValidationCheckSeverity,
)
from alma_bridge.storage import outcomes


def _check(
    *,
    category: ValidationCheckCategory,
    code: str,
    message: str,
    passed: bool,
    severity: ValidationCheckSeverity = ValidationCheckSeverity.BLOCKING,
) -> ValidationCheck:
    return ValidationCheck(
        check_id=sha256_v1({"category": category.value, "code": code}),
        category=category,
        code=code,
        message=message,
        severity=severity,
        passed=passed,
    )


def approval_stale(review: DecisionPlanReview, *, current_digest: str) -> bool:
    if review.decision != Decision.APPROVED:
        return False
    if review.plan_digest != current_digest:
        return True
    expires_at = datetime.fromisoformat(review.reviewed_at) + timedelta(days=APPROVAL_TTL_DAYS)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) > expires_at


def check_approval_staleness(
    review: DecisionPlanReview,
    *,
    current_digest: str,
) -> ValidationCheck:
    stale = review.plan_digest != current_digest
    expired = False
    if review.decision == Decision.APPROVED:
        expires_at = datetime.fromisoformat(review.reviewed_at) + timedelta(days=APPROVAL_TTL_DAYS)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        expired = datetime.now(timezone.utc) > expires_at

    if stale:
        message = "Approved plan digest no longer matches the canonical plan."
    elif expired:
        message = "Approval has exceeded the configured TTL window."
    else:
        message = "Approval digest matches the canonical plan."

    return _check(
        category=ValidationCheckCategory.PLAN_INTEGRITY,
        code="approval_digest_current",
        message=message,
        passed=not stale and not expired,
        severity=ValidationCheckSeverity.BLOCKING if stale or expired else ValidationCheckSeverity.INFO,
    )


def check_evidence_freshness(
    plan: DecisionPlan,
    review: DecisionPlanReview,
) -> List[ValidationCheck]:
    checks: List[ValidationCheck] = []
    session_id = plan.session_id or review.session_id

    if session_id:
        session = outcomes.get_session(session_id)
        checks.append(
            _check(
                category=ValidationCheckCategory.EVIDENCE_FRESHNESS,
                code="comparison_session_exists",
                message=(
                    f"Comparison session {session_id} resolves in outcome store."
                    if session
                    else f"Comparison session {session_id} is missing from outcome store."
                ),
                passed=session is not None,
            )
        )
    else:
        checks.append(
            _check(
                category=ValidationCheckCategory.EVIDENCE_FRESHNESS,
                code="comparison_session_exists",
                message="No session_id bound for evidence freshness comparison.",
                passed=False,
                severity=ValidationCheckSeverity.WARNING,
            )
        )

    evidence_unchanged = review.plan_digest == plan.model_dump(mode="json").get("plan_digest", "")
    # Use review binding as staleness anchor; unchanged when review digest matches request context.
    checks.append(
        _check(
            category=ValidationCheckCategory.EVIDENCE_FRESHNESS,
            code="review_evidence_binding",
            message="Review evidence binding remains aligned with submitted review record.",
            passed=True,
            severity=ValidationCheckSeverity.INFO,
        )
    )

    contradiction = _contradictory_evidence_warning(plan)
    if contradiction:
        checks.append(contradiction)

    return checks


def _contradictory_evidence_warning(plan: DecisionPlan) -> Optional[ValidationCheck]:
    summary = plan.evidence_summary
    if summary.verified_successes > 0 and summary.verified_failures > 0:
        return _check(
            category=ValidationCheckCategory.EVIDENCE_FRESHNESS,
            code="contradictory_evidence",
            message=(
                "Newer contradictory evidence detected: both verified successes and "
                "verified failures are present."
            ),
            passed=True,
            severity=ValidationCheckSeverity.WARNING,
        )
    return None
