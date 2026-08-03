"""Approved plan validation and non-executing dry-run service."""

from __future__ import annotations

from typing import List, Optional

from alma_bridge.decision.models import DecisionInput
from alma_bridge.decision_review.digest import compute_plan_digest, plan_version_for
from alma_bridge.decision_review.policy import _collect_evidence_references
from alma_bridge.decision_review.repository import list_reviews_for_plan
from alma_bridge.decision_review.service import DecisionReviewService
from alma_bridge.decision_validation.errors import (
    DecisionValidationModeError,
    DecisionValidationNotFoundError,
)
from alma_bridge.decision_validation.models import (
    DRY_RUN_DISCLAIMER,
    DecisionPlanDryRunReport,
    ValidationRequest,
)
from alma_bridge.decision_validation.queries import latest_validation, validation_history
from alma_bridge.decision_validation.repository import append_validation, new_validation_id, now_iso
from alma_bridge.decision_validation.status import aggregate_status
from alma_bridge.decision_validation.validators import run_all_validations


class DecisionValidationService:
    """Observational validation for approved decision plans — dry-run only."""

    def __init__(
        self,
        *,
        review_service: DecisionReviewService | None = None,
    ) -> None:
        self._review = review_service or DecisionReviewService()

    def validate_plan(
        self,
        plan_id: str,
        decision_input: DecisionInput,
        request: ValidationRequest,
    ) -> DecisionPlanDryRunReport:
        if request.mode != "dry_run":
            raise DecisionValidationModeError("only dry_run mode is supported")

        detail = self._review.get_plan_detail(plan_id, decision_input)
        plan = detail.plan
        review = self._resolve_review(plan_id, request.review_id)

        checks, approval_stale_flag = run_all_validations(
            plan,
            review,
            submitted_digest=request.plan_digest,
        )
        current_digest = compute_plan_digest(plan)
        if request.plan_digest != current_digest or review.plan_digest != current_digest:
            approval_stale_flag = True
        status, has_warnings = aggregate_status(
            review=review,
            checks=checks,
            approval_stale_flag=approval_stale_flag,
        )

        report = DecisionPlanDryRunReport(
            validation_id=new_validation_id(),
            plan_id=plan.plan_id,
            plan_version=plan_version_for(plan),
            plan_digest=current_digest,
            review_id=review.review_id,
            session_id=request.session_id or plan.session_id,
            application_fingerprint=plan.application_fingerprint,
            status=status,
            has_warnings=has_warnings,
            approval_stale=approval_stale_flag,
            checks=checks,
            validated_at=now_iso(),
            mode="dry_run",
            execution_performed=False,
            mutations_performed=False,
            disclaimer=DRY_RUN_DISCLAIMER,
            evidence_references=_collect_evidence_references(plan),
        )
        saved = append_validation(report)
        try:
            from alma_bridge.evidence.hooks import on_validation_completed

            on_validation_completed(
                plan.application_fingerprint,
                saved.validation_id,
                saved.plan_digest,
            )
        except Exception:
            pass
        return saved

    def list_validations(self, plan_id: str) -> List[DecisionPlanDryRunReport]:
        return validation_history(plan_id)

    def latest_validation(self, plan_id: str) -> Optional[DecisionPlanDryRunReport]:
        return latest_validation(plan_id)

    @staticmethod
    def _resolve_review(plan_id: str, review_id: str):
        reviews = list_reviews_for_plan(plan_id)
        for review in reviews:
            if review.review_id == review_id:
                return review
        raise DecisionValidationNotFoundError(
            f"review {review_id} not found for plan {plan_id}"
        )
