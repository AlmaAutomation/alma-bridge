"""Acceptance criteria management and waivers."""

from __future__ import annotations

from typing import Optional

from alma_bridge.native_lab.errors import WaiverNotAllowedError
from alma_bridge.native_lab.models import (
    AcceptanceCriterionStatus,
    EngineeringAcceptanceCriterion,
    NativeRuntimeEngineeringWorkItem,
    utc_now_iso,
)


def update_acceptance_criterion(
    work_item: NativeRuntimeEngineeringWorkItem,
    criterion_id: str,
    *,
    status: AcceptanceCriterionStatus,
    waiver_reviewer: Optional[str] = None,
    waiver_reason: Optional[str] = None,
    waiver_expires_at: Optional[str] = None,
    evidence_reference_ids: Optional[list[str]] = None,
) -> EngineeringAcceptanceCriterion:
    """Update a single acceptance criterion on a work item."""
    for criterion in work_item.acceptance_criteria:
        if criterion.criterion_id != criterion_id:
            continue
        if status == AcceptanceCriterionStatus.WAIVED:
            _validate_waiver(criterion, waiver_reviewer, waiver_reason)
            criterion.waiver_reviewer = waiver_reviewer
            criterion.waiver_reason = waiver_reason
            criterion.waiver_expires_at = waiver_expires_at
        criterion.status = status
        if evidence_reference_ids is not None:
            criterion.evidence_reference_ids = evidence_reference_ids
        criterion.updated_at = utc_now_iso()
        return criterion
    raise ValueError(f"Acceptance criterion not found: {criterion_id}")


def _validate_waiver(
    criterion: EngineeringAcceptanceCriterion,
    reviewer: Optional[str],
    reason: Optional[str],
) -> None:
    if criterion.security_related or criterion.verification_related:
        if not reviewer or not reason:
            raise WaiverNotAllowedError(
                f"Critical criterion {criterion.criterion_id} requires reviewer and reason for waiver"
            )
    if criterion.critical and not reviewer:
        raise WaiverNotAllowedError(
            f"Critical criterion {criterion.criterion_id} cannot be silently waived"
        )


def satisfied_criteria_count(work_item: NativeRuntimeEngineeringWorkItem) -> int:
    return sum(
        1
        for c in work_item.acceptance_criteria
        if c.status in (AcceptanceCriterionStatus.SATISFIED, AcceptanceCriterionStatus.WAIVED)
    )
