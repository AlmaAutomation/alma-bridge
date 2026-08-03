"""Decision plan review, approval, and export service."""

from __future__ import annotations

import json
from typing import List, Optional
from uuid import uuid4

from alma_bridge.decision.models import Constraint, DecisionInput, DecisionPlan, RecommendationKind
from alma_bridge.decision.service import DecisionService
from alma_bridge.decision_review.digest import compute_plan_digest, plan_version_for
from alma_bridge.decision_review.errors import DecisionPlanMismatchError, DecisionReviewPolicyError
from alma_bridge.decision_review.models import (
    EXPORT_DISCLAIMER,
    EXECUTION_STATUS_NOT_EXECUTED,
    CandidateStep,
    Decision,
    DecisionPlanArtifact,
    DecisionPlanDetail,
    DecisionPlanReview,
    DecisionPlanReviewRequest,
    DecisionPlanSummary,
    ExportRequest,
)
from alma_bridge.decision_review.policy import (
    _collect_evidence_references,
    extract_risks,
    validate_approval_policy,
)
from alma_bridge.decision_review.queries import effective_decision, review_history
from alma_bridge.decision_review.repository import (
    append_export,
    append_review,
    list_reviews_for_plan,
    new_review_id,
    now_iso,
)


class DecisionReviewService:
    """Human review workflow for deterministic decision plans."""

    def __init__(
        self,
        *,
        decision_service: DecisionService | None = None,
    ) -> None:
        self._decision = decision_service or DecisionService()

    def get_plan_detail(
        self,
        plan_id: str,
        decision_input: DecisionInput,
    ) -> DecisionPlanDetail:
        plan = self._decision.plan_from_input(decision_input)
        if plan.plan_id != plan_id:
            raise DecisionPlanMismatchError(
                f"plan_id {plan_id} does not match rebuilt plan {plan.plan_id}"
            )
        digest = compute_plan_digest(plan)
        summary = self.build_summary(plan, digest=digest)
        return DecisionPlanDetail(
            plan=plan,
            plan_version=plan_version_for(plan),
            plan_digest=digest,
            summary=summary,
            execution_status=EXECUTION_STATUS_NOT_EXECUTED,
        )

    def build_summary(
        self,
        plan: DecisionPlan,
        *,
        digest: Optional[str] = None,
    ) -> DecisionPlanSummary:
        plan_digest = digest or compute_plan_digest(plan)
        reviews = list_reviews_for_plan(plan.plan_id)
        latest_decision, approval_stale = effective_decision(
            reviews,
            current_digest=plan_digest,
        )
        objective = self._objective_for(plan)
        confidence = self._aggregate_confidence(plan)
        candidate_steps = self._candidate_steps(plan)
        constraints = self._aggregate_constraints(plan)
        risks = extract_risks(plan)
        return DecisionPlanSummary(
            plan_id=plan.plan_id,
            plan_version=plan_version_for(plan),
            plan_digest=plan_digest,
            session_id=plan.session_id,
            application_fingerprint=plan.application_fingerprint,
            application_name=plan.application_name,
            objective=objective,
            confidence=confidence,
            evidence_summary=plan.evidence_summary,
            candidate_steps=candidate_steps,
            constraints=constraints,
            risks=risks,
            execution_status=EXECUTION_STATUS_NOT_EXECUTED,
            latest_decision=latest_decision,
            approval_stale=approval_stale,
            review_required=True,
        )

    def list_reviews(self, plan_id: str) -> List[DecisionPlanReview]:
        return review_history(plan_id)

    def latest_review(self, plan_id: str) -> Optional[DecisionPlanReview]:
        reviews = review_history(plan_id)
        return reviews[-1] if reviews else None

    def submit_review(
        self,
        plan_id: str,
        decision_input: DecisionInput,
        request: DecisionPlanReviewRequest,
    ) -> DecisionPlanReview:
        detail = self.get_plan_detail(plan_id, decision_input)
        plan = detail.plan
        summary = detail.summary

        if request.decision == Decision.APPROVED:
            result = validate_approval_policy(
                plan=plan,
                summary=summary,
                request=request,
            )
            if not result.allowed:
                raise DecisionReviewPolicyError(
                    "approval policy validation failed",
                    violations=[item.model_dump(mode="json") for item in result.violations],
                )

        review = DecisionPlanReview(
            review_id=new_review_id(),
            plan_id=plan.plan_id,
            application_fingerprint=plan.application_fingerprint,
            session_id=plan.session_id,
            plan_version=detail.plan_version,
            plan_digest=detail.plan_digest,
            decision=request.decision,
            reviewer=request.reviewer,
            reviewed_at=now_iso(),
            comment=request.comment,
            risk_acknowledgements=request.risk_acknowledgements,
            evidence_references=_collect_evidence_references(plan),
        )
        saved = append_review(review)
        try:
            from alma_bridge.evidence.hooks import on_review_submitted

            on_review_submitted(
                plan.application_fingerprint,
                saved.review_id,
                saved.plan_digest,
            )
        except Exception:
            pass
        return saved

    def export_plan(
        self,
        plan_id: str,
        decision_input: DecisionInput,
        request: ExportRequest,
    ) -> DecisionPlanArtifact:
        detail = self.get_plan_detail(plan_id, decision_input)
        if request.plan_digest != detail.plan_digest:
            raise DecisionReviewPolicyError(
                "plan_digest does not match the current canonical plan",
                violations=[{"code": "plan_digest_mismatch", "message": "stale export request"}],
            )

        reviews = review_history(plan_id)
        payload = {
            "plan": detail.plan.model_dump(mode="json"),
            "plan_version": detail.plan_version,
            "plan_digest": detail.plan_digest,
            "summary": detail.summary.model_dump(mode="json"),
            "reviews": [item.model_dump(mode="json") for item in reviews],
            "execution_status": EXECUTION_STATUS_NOT_EXECUTED,
            "disclaimer": EXPORT_DISCLAIMER,
        }

        if request.format == "markdown":
            content = self._render_markdown(detail, reviews)
        else:
            content = json.dumps(payload, indent=2, sort_keys=True)

        artifact = DecisionPlanArtifact(
            artifact_id=str(uuid4()),
            plan_id=plan_id,
            plan_version=detail.plan_version,
            plan_digest=detail.plan_digest,
            format=request.format,
            content=content,
            exported_at=now_iso(),
            disclaimer=EXPORT_DISCLAIMER,
            execution_status=EXECUTION_STATUS_NOT_EXECUTED,
        )
        return append_export(artifact)

    @staticmethod
    def _objective_for(plan: DecisionPlan) -> str:
        if not plan.recommendations:
            return "Review compatibility evidence before any execution planning."
        priority = (
            RecommendationKind.HOLD,
            RecommendationKind.STRATEGY,
            RecommendationKind.REMEDIATION_REVIEW,
            RecommendationKind.VERIFICATION_REVIEW,
            RecommendationKind.ENVIRONMENT,
            RecommendationKind.EVIDENCE_REVIEW,
        )
        by_kind = {item.kind: item for item in plan.recommendations}
        for kind in priority:
            if kind in by_kind:
                return by_kind[kind].action
        return plan.recommendations[0].action

    @staticmethod
    def _aggregate_confidence(plan: DecisionPlan):
        if not plan.recommendations:
            from alma_bridge.decision.models import ConfidenceLevel

            return ConfidenceLevel(level="low", score=0.0, factors=["no_recommendations"])
        best = max(plan.recommendations, key=lambda item: item.confidence.score)
        return best.confidence

    @staticmethod
    def _candidate_steps(plan: DecisionPlan) -> List[CandidateStep]:
        steps: List[CandidateStep] = []
        for recommendation in plan.recommendations:
            steps.append(
                CandidateStep(
                    step_id=recommendation.recommendation_id,
                    kind=recommendation.kind.value,
                    action=recommendation.action,
                    confidence=recommendation.confidence,
                )
            )
        return steps

    @staticmethod
    def _aggregate_constraints(plan: DecisionPlan) -> List[Constraint]:
        merged = {}
        for recommendation in plan.recommendations:
            for constraint in recommendation.constraints:
                merged[(constraint.code, constraint.description)] = constraint
        return sorted(merged.values(), key=lambda item: (item.code, item.description))

    @staticmethod
    def _render_markdown(
        detail: DecisionPlanDetail,
        reviews: List[DecisionPlanReview],
    ) -> str:
        plan = detail.plan
        summary = detail.summary
        lines = [
            "# Decision Plan Export",
            "",
            f"> {EXPORT_DISCLAIMER}",
            "",
            f"- Plan ID: `{plan.plan_id}`",
            f"- Plan version: `{detail.plan_version}`",
            f"- Plan digest: `{detail.plan_digest}`",
            f"- Application: {plan.application_name} (`{plan.application_fingerprint}`)",
            f"- Execution status: {EXECUTION_STATUS_NOT_EXECUTED}",
            "",
            "## Objective",
            summary.objective,
            "",
            "## Confidence",
            f"- Level: {summary.confidence.level}",
            f"- Score: {summary.confidence.score}",
            "",
            "## Candidate steps",
        ]
        for step in summary.candidate_steps:
            lines.append(f"- **{step.kind}**: {step.action}")
        lines.extend(["", "## Constraints"])
        for constraint in summary.constraints:
            lines.append(f"- `{constraint.code}`: {constraint.description}")
        lines.extend(["", "## Risks"])
        for risk in summary.risks:
            lines.append(f"- [{risk.severity}] {risk.summary}")
        lines.extend(["", "## Review history"])
        if not reviews:
            lines.append("- No reviews recorded.")
        else:
            for review in reviews:
                lines.append(
                    f"- {review.reviewed_at}: **{review.decision.value}** by {review.reviewer}"
                )
                if review.comment:
                    lines.append(f"  - Comment: {review.comment}")
        return "\n".join(lines) + "\n"
