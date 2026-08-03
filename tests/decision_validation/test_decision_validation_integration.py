"""Integration tests for approved plan validation and dry-run."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from alma_bridge.config import settings
from alma_bridge.decision.models import DecisionInput
from alma_bridge.decision.service import DecisionService
from alma_bridge.decision_review.digest import compute_plan_digest
from alma_bridge.decision_review.models import Decision, DecisionPlanReviewRequest
from alma_bridge.decision_review.policy import extract_risks
from alma_bridge.decision_review.service import DecisionReviewService
from alma_bridge.decision_validation.models import (
    DRY_RUN_DISCLAIMER,
    PlanValidationStatus,
    ValidationRequest,
)
from alma_bridge.decision_validation.service import DecisionValidationService
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
    return DecisionService().plan_for_session(KNOWLEDGE_SESSION_C)


@pytest.fixture
def review_service():
    return DecisionReviewService()


@pytest.fixture
def validation_service():
    return DecisionValidationService()


def _risk_acknowledgements(plan):
    return [risk.risk_id for risk in extract_risks(plan)]


def _approve_and_get_review(plan, review_service):
    review = review_service.submit_review(
        plan.plan_id,
        DecisionInput(session_id=KNOWLEDGE_SESSION_C),
        DecisionPlanReviewRequest(
            decision=Decision.APPROVED,
            reviewer="operator-a",
            comment="Approved for validation testing.",
            risk_acknowledgements=_risk_acknowledgements(plan),
            plan_digest=compute_plan_digest(plan),
        ),
    )
    return review


def _validation_request(plan, review, **overrides):
    payload = {
        "plan_digest": compute_plan_digest(plan),
        "review_id": review.review_id,
        "session_id": KNOWLEDGE_SESSION_C,
        "mode": "dry_run",
    }
    payload.update(overrides)
    return ValidationRequest(**payload)


def _mock_runtime_ok(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/wine" if cmd == "wine" else None)


def _mock_path_exists(monkeypatch, exists=True):
    original_exists = Path.exists

    def _exists(self):
        path = str(self)
        if path.endswith("codeblocks.exe") or "/tmp/prefix" in path:
            return exists
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", _exists)


def _session_with_overrides(session_id, **updates):
    session = outcomes.get_session(session_id)
    if not session:
        return session
    patched = dict(session)
    for key, value in updates.items():
        patched[key] = value
    return patched


def _patch_session(monkeypatch, session_id, patched_session):
    original_get_session = outcomes.get_session

    def _get_session(sid):
        if sid == session_id:
            return patched_session
        return original_get_session(sid)

    for target in (
        "alma_bridge.storage.outcomes.get_session",
        "alma_bridge.decision_validation.validators.outcomes.get_session",
        "alma_bridge.decision_validation.capability_check.outcomes.get_session",
        "alma_bridge.decision_validation.policy_check.outcomes.get_session",
        "alma_bridge.decision_validation.staleness.outcomes.get_session",
    ):
        monkeypatch.setattr(target, _get_session)


class TestDecisionValidationBackend:
    def test_approved_exact_digest_validates(
        self, seeded_plan, review_service, validation_service, monkeypatch
    ):
        _mock_runtime_ok(monkeypatch)
        _mock_path_exists(monkeypatch, exists=True)
        review = _approve_and_get_review(seeded_plan, review_service)
        report = validation_service.validate_plan(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            _validation_request(seeded_plan, review),
        )
        assert report.status == PlanValidationStatus.VALID
        assert report.approval_stale is False
        assert report.execution_performed is False
        assert report.mutations_performed is False

    def test_stale_approval_returns_stale(
        self, seeded_plan, review_service, validation_service, monkeypatch
    ):
        _mock_runtime_ok(monkeypatch)
        review = _approve_and_get_review(seeded_plan, review_service)
        mutated_digest = "sha256:deadbeef"
        report = validation_service.validate_plan(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            _validation_request(seeded_plan, review, plan_digest=mutated_digest),
        )
        assert report.status == PlanValidationStatus.STALE
        assert report.approval_stale is True

    def test_unapproved_plan_cannot_validate_as_valid(
        self, seeded_plan, review_service, validation_service, monkeypatch
    ):
        _mock_runtime_ok(monkeypatch)
        review = review_service.submit_review(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            DecisionPlanReviewRequest(
                decision=Decision.REJECTED,
                reviewer="operator-b",
                comment="Rejected.",
                plan_digest=compute_plan_digest(seeded_plan),
            ),
        )
        report = validation_service.validate_plan(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            _validation_request(seeded_plan, review),
        )
        assert report.status == PlanValidationStatus.INVALID

    def test_missing_evidence_blocks_validation(self, seeded_plan, review_service, validation_service, monkeypatch):
        _mock_runtime_ok(monkeypatch)
        plan = seeded_plan.model_copy(deep=True)
        for recommendation in plan.recommendations:
            recommendation.provenance = []
        review = review_service.submit_review(
            plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            DecisionPlanReviewRequest(
                decision=Decision.APPROVED,
                reviewer="operator-a",
                comment="Approved without evidence.",
                risk_acknowledgements=_risk_acknowledgements(seeded_plan),
                plan_digest=compute_plan_digest(seeded_plan),
            ),
        )
        detail = review_service.get_plan_detail(
            plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
        )
        detail = detail.model_copy(update={"plan": plan})
        monkeypatch.setattr(
            "alma_bridge.decision_validation.service.DecisionReviewService.get_plan_detail",
            lambda *_args, **_kwargs: detail,
        )
        report = validation_service.validate_plan(
            plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            _validation_request(plan, review),
        )
        assert report.status in {
            PlanValidationStatus.BLOCKED,
            PlanValidationStatus.INVALID,
            PlanValidationStatus.STALE,
        }
        assert any(check.code == "evidence_resolves" and not check.passed for check in report.checks)

    def test_runtime_unavailable_blocks_validation(
        self, seeded_plan, review_service, validation_service, monkeypatch
    ):
        monkeypatch.setattr("shutil.which", lambda _cmd: None)
        review = _approve_and_get_review(seeded_plan, review_service)
        report = validation_service.validate_plan(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            _validation_request(seeded_plan, review),
        )
        assert report.status == PlanValidationStatus.BLOCKED
        assert any(
            check.category.value == "runtime_feasibility" and not check.passed
            for check in report.checks
        )

    def test_architecture_mismatch_blocks_validation(
        self, seeded_plan, review_service, validation_service, monkeypatch
    ):
        _mock_runtime_ok(monkeypatch)
        review = _approve_and_get_review(seeded_plan, review_service)
        patched_session = _session_with_overrides(
            KNOWLEDGE_SESSION_C,
            hardware_profile={"architecture": "arm64"},
        )
        _patch_session(monkeypatch, KNOWLEDGE_SESSION_C, patched_session)
        with patch("platform.machine", return_value="x86_64"):
            report = validation_service.validate_plan(
                seeded_plan.plan_id,
                DecisionInput(session_id=KNOWLEDGE_SESSION_C),
                _validation_request(seeded_plan, review),
            )
        assert report.status == PlanValidationStatus.BLOCKED
        assert any(check.code == "architecture_supported" and not check.passed for check in report.checks)

    def test_missing_verification_contract_blocks_validation(
        self, seeded_plan, review_service, validation_service, monkeypatch
    ):
        _mock_runtime_ok(monkeypatch)
        _mock_path_exists(monkeypatch, exists=True)
        review = _approve_and_get_review(seeded_plan, review_service)
        detail = review_service.get_plan_detail(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
        )
        patched_session = _session_with_overrides(KNOWLEDGE_SESSION_C)
        attempts = [dict(item) for item in patched_session.get("attempts", [])]
        for attempt in attempts:
            attempt["verification"] = {}
        patched_session["attempts"] = attempts
        _patch_session(monkeypatch, KNOWLEDGE_SESSION_C, patched_session)
        monkeypatch.setattr(
            "alma_bridge.decision_validation.service.DecisionReviewService.get_plan_detail",
            lambda *_args, **_kwargs: detail,
        )
        report = validation_service.validate_plan(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            _validation_request(seeded_plan, review),
        )
        assert report.status == PlanValidationStatus.BLOCKED
        assert any(
            check.code == "verification_contract_supported" and not check.passed
            for check in report.checks
        )

    def test_policy_denial_reported_without_mutation(
        self, seeded_plan, review_service, validation_service, monkeypatch
    ):
        monkeypatch.setattr(settings, "operator_allow_mutations", False)
        review = _approve_and_get_review(seeded_plan, review_service)
        report = validation_service.validate_plan(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            _validation_request(seeded_plan, review),
        )
        assert report.mutations_performed is False
        assert any(check.code == "prefix_mutation_policy_simulation" for check in report.checks)

    def test_campaign_guard_reported_without_execution(
        self, seeded_plan, review_service, validation_service, monkeypatch, tmp_path
    ):
        disposable = tmp_path / "disposable"
        disposable.mkdir()
        monkeypatch.setattr(settings, "validation_campaign_mode", True)
        monkeypatch.setattr(settings, "validation_campaign_disposable_root", str(disposable))
        monkeypatch.setattr(settings, "validation_campaign_id", "test-campaign")
        review = _approve_and_get_review(seeded_plan, review_service)
        report = validation_service.validate_plan(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            _validation_request(seeded_plan, review),
        )
        assert report.execution_performed is False
        assert any(check.code == "campaign_guard_violation" for check in report.checks)

    def test_legacy_unknown_environment_indeterminate(
        self, seeded_plan, review_service, validation_service, monkeypatch
    ):
        _mock_runtime_ok(monkeypatch)
        _mock_path_exists(monkeypatch, exists=True)
        patched_session = _session_with_overrides(KNOWLEDGE_SESSION_C)
        attempts = [dict(item) for item in patched_session.get("attempts", [])]
        attempts[-1]["env"] = dict(attempts[-1].get("env") or {})
        attempts[-1]["env"]["LEGACY_UNKNOWN_FIELD"] = "mystery"
        patched_session["attempts"] = attempts
        _patch_session(monkeypatch, KNOWLEDGE_SESSION_C, patched_session)
        review = _approve_and_get_review(seeded_plan, review_service)
        report = validation_service.validate_plan(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            _validation_request(seeded_plan, review),
        )
        assert report.status == PlanValidationStatus.INDETERMINATE
        assert any(check.code == "legacy_unknown_environment" for check in report.checks)

    def test_newer_contradictory_evidence_warning(
        self, seeded_plan, review_service, validation_service, monkeypatch
    ):
        _mock_runtime_ok(monkeypatch)
        _mock_path_exists(monkeypatch, exists=True)
        plan = seeded_plan.model_copy(deep=True)
        plan.evidence_summary.verified_successes = 2
        plan.evidence_summary.verified_failures = 1
        review = _approve_and_get_review(seeded_plan, review_service)
        detail = review_service.get_plan_detail(
            plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
        )
        detail = detail.model_copy(update={"plan": plan})
        monkeypatch.setattr(
            "alma_bridge.decision_validation.service.DecisionReviewService.get_plan_detail",
            lambda *_args, **_kwargs: detail,
        )
        report = validation_service.validate_plan(
            plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            _validation_request(plan, review),
        )
        assert any(check.code == "contradictory_evidence" for check in report.checks)

    def test_validation_writes_only_validation_records(
        self, seeded_plan, review_service, validation_service, monkeypatch, tmp_path
    ):
        _mock_runtime_ok(monkeypatch)
        review = _approve_and_get_review(seeded_plan, review_service)
        before_reviews = len(review_service.list_reviews(seeded_plan.plan_id))
        validation_service.validate_plan(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            _validation_request(seeded_plan, review),
        )
        assert len(review_service.list_reviews(seeded_plan.plan_id)) == before_reviews
        with sqlite3.connect(settings.db_path) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert "decision_plan_validations" in tables

    def test_no_bridge_session_attempt_mutation(
        self, seeded_plan, review_service, validation_service, monkeypatch
    ):
        _mock_runtime_ok(monkeypatch)
        session_before = outcomes.get_session(KNOWLEDGE_SESSION_C)
        attempts_before = len(session_before.get("attempts", []))
        review = _approve_and_get_review(seeded_plan, review_service)
        validation_service.validate_plan(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            _validation_request(seeded_plan, review),
        )
        session_after = outcomes.get_session(KNOWLEDGE_SESSION_C)
        assert len(session_after.get("attempts", [])) == attempts_before

    def test_no_subprocess_launch(self, seeded_plan, review_service, validation_service, monkeypatch):
        review = _approve_and_get_review(seeded_plan, review_service)

        def _forbidden(*args, **kwargs):
            raise AssertionError("subprocess launch forbidden during validation dry-run")

        with patch("subprocess.run", side_effect=_forbidden):
            with patch("subprocess.Popen", side_effect=_forbidden):
                report = validation_service.validate_plan(
                    seeded_plan.plan_id,
                    DecisionInput(session_id=KNOWLEDGE_SESSION_C),
                    _validation_request(seeded_plan, review),
                )
        assert report.execution_performed is False

    def test_execution_performed_always_false(
        self, seeded_plan, review_service, validation_service, monkeypatch
    ):
        _mock_runtime_ok(monkeypatch)
        review = _approve_and_get_review(seeded_plan, review_service)
        report = validation_service.validate_plan(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            _validation_request(seeded_plan, review),
        )
        assert report.execution_performed is False

    def test_mutations_performed_always_false(
        self, seeded_plan, review_service, validation_service, monkeypatch
    ):
        _mock_runtime_ok(monkeypatch)
        review = _approve_and_get_review(seeded_plan, review_service)
        report = validation_service.validate_plan(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            _validation_request(seeded_plan, review),
        )
        assert report.mutations_performed is False

    def test_validation_history_append_only(
        self, seeded_plan, review_service, validation_service, monkeypatch
    ):
        _mock_runtime_ok(monkeypatch)
        review = _approve_and_get_review(seeded_plan, review_service)
        first = validation_service.validate_plan(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            _validation_request(seeded_plan, review),
        )
        second = validation_service.validate_plan(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            _validation_request(seeded_plan, review),
        )
        history = validation_service.list_validations(seeded_plan.plan_id)
        assert len(history) == 2
        assert history[0].validation_id == first.validation_id
        assert history[1].validation_id == second.validation_id
        latest = validation_service.latest_validation(seeded_plan.plan_id)
        assert latest.validation_id == second.validation_id

    def test_codeblocks_session_c_acceptance_scenario(
        self, seeded_plan, review_service, validation_service, monkeypatch
    ):
        _mock_runtime_ok(monkeypatch)
        _mock_path_exists(monkeypatch, exists=True)
        assert seeded_plan.session_id == KNOWLEDGE_SESSION_C
        assert seeded_plan.application_fingerprint == CODEBLOCKS_FINGERPRINT
        review = _approve_and_get_review(seeded_plan, review_service)
        report = validation_service.validate_plan(
            seeded_plan.plan_id,
            DecisionInput(session_id=KNOWLEDGE_SESSION_C),
            _validation_request(seeded_plan, review),
        )
        assert report.disclaimer == DRY_RUN_DISCLAIMER
        assert report.execution_performed is False
        assert report.mutations_performed is False
        assert report.status in {
            PlanValidationStatus.VALID,
            PlanValidationStatus.INDETERMINATE,
            PlanValidationStatus.BLOCKED,
        }

    def test_api_validate_and_list(self, seeded_plan, review_service, monkeypatch):
        _mock_runtime_ok(monkeypatch)
        client = TestClient(create_app())
        review = _approve_and_get_review(seeded_plan, review_service)
        response = client.post(
            f"/bridge/decision/plans/{seeded_plan.plan_id}/validate",
            params={"session_id": KNOWLEDGE_SESSION_C},
            json={
                "plan_digest": compute_plan_digest(seeded_plan),
                "review_id": review.review_id,
                "session_id": KNOWLEDGE_SESSION_C,
                "mode": "dry_run",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["execution_performed"] is False
        assert payload["mutations_performed"] is False
        assert DRY_RUN_DISCLAIMER in payload["disclaimer"]

        listed = client.get(
            f"/bridge/decision/plans/{seeded_plan.plan_id}/validations",
            params={"session_id": KNOWLEDGE_SESSION_C},
        )
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        latest = client.get(
            f"/bridge/decision/plans/{seeded_plan.plan_id}/validation/latest",
            params={"session_id": KNOWLEDGE_SESSION_C},
        )
        assert latest.status_code == 200
