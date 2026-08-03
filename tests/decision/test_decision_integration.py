"""Integration tests for the Decision Engine."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from alma_bridge.decision.models import DECISION_SCHEMA_VERSION
from alma_bridge.decision.service import DecisionService
from alma_bridge.main import create_app
from alma_bridge.storage import outcomes
from tests.catalog.conftest import APP_A_FINGERPRINT
from tests.comparison.conftest import (
    COMPARE_BASELINE_SESSION,
    COMPARE_COMPARISON_SESSION,
    seed_codeblocks_comparison_acceptance,
)
from tests.intelligence.conftest import CODEBLOCKS_FINGERPRINT
from tests.regression.conftest import KNOWLEDGE_SESSION_C, seed_codeblocks_regression_sessions


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    outcomes.init_outcome_store()
    yield


def _assert_recommendation_contract(payload: dict) -> None:
    for recommendation in payload["recommendations"]:
        assert recommendation.get("confidence") is not None
        assert recommendation["confidence"]["level"] in {"high", "medium", "low"}
        assert 0.0 <= recommendation["confidence"]["score"] <= 1.0
        assert recommendation.get("constraints")
        assert recommendation.get("provenance")
        assert recommendation["human_approval_required"] is True
        assert recommendation.get("approval_reasons")


class TestDecisionIntegration:
    def test_plan_for_application_with_regression_evidence(self):
        seed_codeblocks_regression_sessions()
        plan = DecisionService().plan_for_application(CODEBLOCKS_FINGERPRINT)
        assert plan.schema_version == DECISION_SCHEMA_VERSION
        assert plan.application_fingerprint == CODEBLOCKS_FINGERPRINT
        assert plan.recommendations
        _assert_recommendation_contract(plan.model_dump(mode="json"))

    def test_plan_for_session(self):
        seed_codeblocks_regression_sessions()
        plan = DecisionService().plan_for_session(KNOWLEDGE_SESSION_C)
        assert plan.session_id == KNOWLEDGE_SESSION_C
        assert plan.recommendations
        _assert_recommendation_contract(plan.model_dump(mode="json"))

    def test_hold_when_insufficient_evidence(self):
        from tests.intelligence.conftest import seed_codeblocks_session

        seed_codeblocks_session()
        plan = DecisionService().plan_for_application(CODEBLOCKS_FINGERPRINT)
        kinds = {item.kind.value for item in plan.recommendations}
        assert "hold" in kinds
        hold = next(item for item in plan.recommendations if item.kind.value == "hold")
        assert hold.human_approval_required is True
        assert "insufficient_evidence" in hold.approval_reasons

    def test_comparison_includes_environment_recommendation(self):
        seed_codeblocks_comparison_acceptance()
        plan = DecisionService().plan_for_application(
            APP_A_FINGERPRINT,
            baseline_session_id=COMPARE_BASELINE_SESSION,
            comparison_session_id=COMPARE_COMPARISON_SESSION,
        )
        assert plan.evidence_summary.comparison_included is True
        kinds = {item.kind.value for item in plan.recommendations}
        assert "environment" in kinds

    def test_api_get_plan(self):
        seed_codeblocks_regression_sessions()
        client = TestClient(create_app())
        response = client.get(
            "/bridge/decision/plan",
            params={
                "application_fingerprint": CODEBLOCKS_FINGERPRINT,
                "session_id": KNOWLEDGE_SESSION_C,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["schema_version"] == DECISION_SCHEMA_VERSION
        _assert_recommendation_contract(payload)

    def test_api_post_plan(self):
        seed_codeblocks_regression_sessions()
        client = TestClient(create_app())
        response = client.post(
            "/bridge/decision/plan",
            json={
                "application_fingerprint": CODEBLOCKS_FINGERPRINT,
                "ask_question": "What verification history exists?",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["evidence_summary"]["ask_context_included"] is True
        _assert_recommendation_contract(payload)

    def test_api_404_when_missing(self):
        client = TestClient(create_app())
        response = client.get(
            "/bridge/decision/plan",
            params={"application_fingerprint": "missing-fingerprint"},
        )
        assert response.status_code == 404

    def test_decision_does_not_record_attempts(self):
        seed_codeblocks_regression_sessions()
        client = TestClient(create_app())
        with patch("alma_bridge.storage.outcomes.record_attempt") as record_attempt:
            response = client.get(
                "/bridge/decision/plan",
                params={"application_fingerprint": CODEBLOCKS_FINGERPRINT},
            )
            assert response.status_code == 200
            record_attempt.assert_not_called()

    def test_no_auto_execute_language(self):
        seed_codeblocks_regression_sessions()
        plan = DecisionService().plan_for_application(CODEBLOCKS_FINGERPRINT)
        serialized = plan.model_dump_json().lower()
        for banned in ("auto-execute", "auto execute", "alma recommends", "you should"):
            assert banned not in serialized
