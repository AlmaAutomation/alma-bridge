"""Integration and policy tests for decision plan review."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from alma_bridge.decision.models import DecisionInput
from alma_bridge.decision.service import DecisionService
from alma_bridge.decision_review.digest import compute_plan_digest
from alma_bridge.decision_review.models import (
    EXPORT_DISCLAIMER,
    EXECUTION_STATUS_NOT_EXECUTED,
    Decision,
    DecisionPlanReviewRequest,
    ExportRequest,
)
from alma_bridge.decision_review.policy import extract_risks, validate_approval_policy
from alma_bridge.decision_review.service import DecisionReviewService
from alma_bridge.main import create_app
from alma_bridge.storage import outcomes
from tests.intelligence.conftest import CODEBLOCKS_FINGERPRINT
from tests.regression.conftest import KNOWLEDGE_SESSION_C, seed_codeblocks_regression_sessions


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    outcomes.init_outcome_store()
    yield


@pytest.fixture
def seeded_plan():
    seed_codeblocks_regression_sessions()
    plan = DecisionService().plan_for_session(KNOWLEDGE_SESSION_C)
    return plan


@pytest.fixture
def review_service():
    return DecisionReviewService()


def _risk_acknowledgements(plan):
    return [risk.risk_id for risk in extract_risks(plan)]


def _approve_request(plan, **overrides):
    payload = {
        "decision": "approved",
        "reviewer": "operator-a",
        "comment": "Reviewed evidence and constraints.",
        "risk_acknowledgements": _risk_acknowledgements(plan),
        "plan_digest": compute_plan_digest(plan),
    }
    payload.update(overrides)
    return DecisionPlanReviewRequest(**payload)


class TestDecisionReviewBackend:
    def test_plan_digest_is_deterministic_excluding_generated_at(self, seeded_plan):
        digest_a = compute_plan_digest(seeded_plan)
        digest_b = compute_plan_digest(seeded_plan)
        assert digest_a == digest_b
        assert digest_a.startswith("sha256:")

    def test_get_plan_detail_by_plan_id(self, seeded_plan, review_service):
        detail = review_service.get_plan_detail(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
        )
        assert detail.plan.plan_id == seeded_plan.plan_id
        assert detail.execution_status == EXECUTION_STATUS_NOT_EXECUTED
        assert detail.summary.candidate_steps

    def test_plan_id_mismatch_returns_error(self, seeded_plan, review_service):
        from alma_bridge.decision_review.errors import DecisionPlanMismatchError

        with pytest.raises(DecisionPlanMismatchError):
            review_service.get_plan_detail(
                "wrong-plan-id",
                DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            )

    def test_submit_approved_review(self, seeded_plan, review_service):
        review = review_service.submit_review(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            _approve_request(seeded_plan),
        )
        assert review.decision == Decision.APPROVED
        assert review.plan_digest == compute_plan_digest(seeded_plan)
        assert review.evidence_references

    def test_submit_rejected_review(self, seeded_plan, review_service):
        review = review_service.submit_review(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            DecisionPlanReviewRequest(
                decision=Decision.REJECTED,
                reviewer="operator-b",
                comment="Insufficient verification depth.",
                plan_digest=compute_plan_digest(seeded_plan),
            ),
        )
        assert review.decision == Decision.REJECTED

    def test_submit_needs_revision_review(self, seeded_plan, review_service):
        review = review_service.submit_review(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            DecisionPlanReviewRequest(
                decision=Decision.NEEDS_REVISION,
                reviewer="operator-c",
                comment="Need comparison evidence.",
                plan_digest=compute_plan_digest(seeded_plan),
            ),
        )
        assert review.decision == Decision.NEEDS_REVISION

    def test_approval_fails_without_evidence_references(self, seeded_plan, review_service):
        summary = review_service.build_summary(seeded_plan)
        request = _approve_request(seeded_plan)
        plan = seeded_plan.model_copy(deep=True)
        for recommendation in plan.recommendations:
            recommendation.provenance = []
        result = validate_approval_policy(plan=plan, summary=summary, request=request)
        assert not result.allowed
        assert any(item.code == "evidence_references_required" for item in result.violations)

    def test_approval_requires_verification_acknowledgement(self, seeded_plan):
        plan = seeded_plan.model_copy(deep=True)
        for recommendation in plan.recommendations:
            recommendation.approval_reasons = [
                reason for reason in recommendation.approval_reasons if reason != "verification_required"
            ]
            recommendation.constraints = [
                item
                for item in recommendation.constraints
                if item.code != "verification_authority_required"
            ]
        summary = DecisionReviewService().build_summary(plan)
        request = _approve_request(seeded_plan)
        result = validate_approval_policy(plan=plan, summary=summary, request=request)
        assert not result.allowed
        assert any(item.code == "verification_required_after_execution" for item in result.violations)

    def test_approval_rejects_automatic_remediation_language(self, seeded_plan):
        plan = seeded_plan.model_copy(deep=True)
        plan.recommendations[0].action = "auto-remediate prefix dependencies now"
        summary = DecisionReviewService().build_summary(plan)
        request = _approve_request(seeded_plan)
        result = validate_approval_policy(plan=plan, summary=summary, request=request)
        assert not result.allowed
        assert any(item.code == "no_automatic_remediation" for item in result.violations)

    def test_approval_rejects_direct_mutation_instruction(self, seeded_plan):
        plan = seeded_plan.model_copy(deep=True)
        plan.recommendations[0].kind = plan.recommendations[0].kind  # keep kind
        from alma_bridge.decision.models import RecommendationKind

        plan.recommendations[0].kind = RecommendationKind.STRATEGY
        plan.recommendations[0].action = "Execute install immediately"
        summary = DecisionReviewService().build_summary(plan)
        request = _approve_request(seeded_plan)
        result = validate_approval_policy(plan=plan, summary=summary, request=request)
        assert not result.allowed
        assert any(item.code == "no_direct_mutation_instruction" for item in result.violations)

    def test_approval_rejects_confidence_without_evidence(self, seeded_plan):
        plan = seeded_plan.model_copy(deep=True)
        for recommendation in plan.recommendations:
            recommendation.provenance = []
            recommendation.confidence.score = 0.95
            recommendation.confidence.level = "high"
        summary = DecisionReviewService().build_summary(plan)
        request = _approve_request(seeded_plan)
        result = validate_approval_policy(plan=plan, summary=summary, request=request)
        assert not result.allowed
        assert any(item.code == "confidence_not_substitute_for_evidence" for item in result.violations)

    def test_approval_requires_risk_acknowledgements(self, seeded_plan, review_service):
        from alma_bridge.decision_review.errors import DecisionReviewPolicyError

        with pytest.raises(DecisionReviewPolicyError) as exc:
            review_service.submit_review(
                seeded_plan.plan_id,
                DecisionInput(session_id=KNOWLEDGE_SESSION_C),
                DecisionPlanReviewRequest(
                    decision=Decision.APPROVED,
                    reviewer="operator-a",
                    comment="Missing risk acks",
                    risk_acknowledgements=[],
                    plan_digest=compute_plan_digest(seeded_plan),
                ),
            )
        assert any(
            item["code"] == "risk_acknowledgements_incomplete"
            for item in exc.value.violations
        )

    def test_approval_requires_matching_plan_digest(self, seeded_plan, review_service):
        from alma_bridge.decision_review.errors import DecisionReviewPolicyError

        with pytest.raises(DecisionReviewPolicyError) as exc:
            review_service.submit_review(
                seeded_plan.plan_id,
                DecisionInput(session_id=KNOWLEDGE_SESSION_C),
                _approve_request(seeded_plan, plan_digest="sha256:deadbeef"),
            )
        assert any(item["code"] == "plan_digest_mismatch" for item in exc.value.violations)

    def test_stale_approval_when_digest_changes(self, seeded_plan, review_service):
        review_service.submit_review(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            _approve_request(seeded_plan),
        )
        mutated = seeded_plan.model_copy(deep=True)
        mutated.notices = sorted(set(mutated.notices) | {"Additional operator notice."})
        summary = review_service.build_summary(mutated)
        assert summary.approval_stale is True

    def test_review_history_and_latest(self, seeded_plan, review_service):
        review_service.submit_review(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            _approve_request(seeded_plan),
        )
        review_service.submit_review(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            DecisionPlanReviewRequest(
                decision=Decision.NEEDS_REVISION,
                reviewer="operator-d",
                comment="Follow-up",
                plan_digest=compute_plan_digest(seeded_plan),
            ),
        )
        history = review_service.list_reviews(seeded_plan.plan_id)
        assert len(history) == 2
        latest = review_service.latest_review(seeded_plan.plan_id)
        assert latest.decision == Decision.NEEDS_REVISION

    def test_export_json_includes_disclaimer(self, seeded_plan, review_service):
        artifact = review_service.export_plan(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            ExportRequest(format="json", plan_digest=compute_plan_digest(seeded_plan)),
        )
        assert artifact.disclaimer == EXPORT_DISCLAIMER
        payload = json.loads(artifact.content)
        assert payload["execution_status"] == EXECUTION_STATUS_NOT_EXECUTED
        assert payload["disclaimer"] == EXPORT_DISCLAIMER

    def test_export_markdown_includes_disclaimer(self, seeded_plan, review_service):
        artifact = review_service.export_plan(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            ExportRequest(format="markdown", plan_digest=compute_plan_digest(seeded_plan)),
        )
        assert EXPORT_DISCLAIMER in artifact.content
        assert "not_executed" in artifact.content

    def test_api_get_plan_endpoint(self, seeded_plan):
        client = TestClient(create_app())
        response = client.get(
            f"/bridge/decision/plans/{seeded_plan.plan_id}",
            params={"session_id": KNOWLEDGE_SESSION_C},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["execution_status"] == EXECUTION_STATUS_NOT_EXECUTED
        assert payload["summary"]["plan_digest"].startswith("sha256:")

    def test_api_submit_and_list_reviews(self, seeded_plan):
        client = TestClient(create_app())
        digest = compute_plan_digest(seeded_plan)
        risks = [risk.risk_id for risk in extract_risks(seeded_plan)]
        submit = client.post(
            f"/bridge/decision/plans/{seeded_plan.plan_id}/reviews",
            params={"session_id": KNOWLEDGE_SESSION_C},
            json={
                "decision": "approved",
                "reviewer": "operator-api",
                "comment": "API approval",
                "risk_acknowledgements": risks,
                "plan_digest": digest,
            },
        )
        assert submit.status_code == 200
        listed = client.get(
            f"/bridge/decision/plans/{seeded_plan.plan_id}/reviews",
            params={"session_id": KNOWLEDGE_SESSION_C},
        )
        assert listed.status_code == 200
        assert len(listed.json()) == 1
        latest = client.get(
            f"/bridge/decision/plans/{seeded_plan.plan_id}/review/latest",
            params={"session_id": KNOWLEDGE_SESSION_C},
        )
        assert latest.status_code == 200
        assert latest.json()["decision"] == "approved"

    def test_api_export_markdown(self, seeded_plan):
        client = TestClient(create_app())
        response = client.post(
            f"/bridge/decision/plans/{seeded_plan.plan_id}/export",
            params={"session_id": KNOWLEDGE_SESSION_C},
            json={
                "format": "markdown",
                "plan_digest": compute_plan_digest(seeded_plan),
            },
        )
        assert response.status_code == 200
        assert EXPORT_DISCLAIMER in response.text

    def test_codeblocks_session_c_acceptance_scenario(self, seeded_plan):
        assert seeded_plan.session_id == KNOWLEDGE_SESSION_C
        assert seeded_plan.application_fingerprint == CODEBLOCKS_FINGERPRINT
        detail = DecisionReviewService().get_plan_detail(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
        )
        assert detail.summary.execution_status == EXECUTION_STATUS_NOT_EXECUTED
        assert detail.summary.review_required is True
