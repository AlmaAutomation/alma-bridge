"""Structured security and semantic risk reviews."""

from __future__ import annotations

import uuid

from alma_bridge.native_lab.digest import digest_of
from alma_bridge.native_lab.models import (
    RiskCategory,
    RiskReviewRecord,
    RiskSeverity,
)


def create_risk_review(
    work_item_id: str,
    *,
    category: RiskCategory,
    severity: RiskSeverity,
    description: str,
    likelihood: str = "medium",
    mitigation: str = "",
    residual_risk: str = "",
    evidence_reference_ids: list[str] | None = None,
    reviewer: str = "",
) -> RiskReviewRecord:
    """Create a structured risk review record."""
    review_id = f"rr_{uuid.uuid4().hex[:12]}"
    body = {
        "review_id": review_id,
        "work_item_id": work_item_id,
        "category": category.value,
        "severity": severity.value,
        "description": description,
    }
    return RiskReviewRecord(
        review_id=review_id,
        work_item_id=work_item_id,
        category=category,
        severity=severity,
        likelihood=likelihood,
        description=description,
        mitigation=mitigation,
        residual_risk=residual_risk,
        evidence_reference_ids=evidence_reference_ids or [],
        reviewer=reviewer,
        review_digest=digest_of(body),
    )
