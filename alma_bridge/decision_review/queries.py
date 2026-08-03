"""Query helpers for decision plan review history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from alma_bridge.decision_review.digest import compute_plan_digest
from alma_bridge.decision_review.models import (
    APPROVAL_TTL_DAYS,
    Decision,
    DecisionPlanReview,
)
from alma_bridge.decision_review.repository import latest_review_for_plan, list_reviews_for_plan


def review_history(plan_id: str) -> List[DecisionPlanReview]:
    return list_reviews_for_plan(plan_id)


def latest_review(plan_id: str) -> Optional[DecisionPlanReview]:
    return latest_review_for_plan(plan_id)


def effective_decision(
    reviews: List[DecisionPlanReview],
    *,
    current_digest: str,
) -> tuple[Optional[Decision], bool]:
    """Return latest substantive decision and whether an approval is stale."""
    if not reviews:
        return None, False

    latest = reviews[-1]
    stale = False

    approved = [item for item in reviews if item.decision == Decision.APPROVED]
    if approved:
        last_approved = approved[-1]
        if last_approved.plan_digest != current_digest:
            stale = True
        expires_at = datetime.fromisoformat(last_approved.reviewed_at) + timedelta(
            days=APPROVAL_TTL_DAYS
        )
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            return Decision.EXPIRED, stale

    return latest.decision, stale


def is_approval_stale(reviews: List[DecisionPlanReview], *, current_digest: str) -> bool:
    approved = [item for item in reviews if item.decision == Decision.APPROVED]
    if not approved:
        return False
    return approved[-1].plan_digest != current_digest
