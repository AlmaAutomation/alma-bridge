"""Determinism tests for the Decision Engine."""

from __future__ import annotations

import pytest

from alma_bridge.decision.models import DecisionInput
from alma_bridge.decision.service import DecisionService
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


def test_same_input_produces_identical_plan():
    seed_codeblocks_regression_sessions()
    service = DecisionService()
    decision_input = DecisionInput(
        application_fingerprint=CODEBLOCKS_FINGERPRINT,
        session_id=KNOWLEDGE_SESSION_C,
    )
    first = service.plan_from_input(decision_input)
    second = service.plan_from_input(decision_input)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_plan_id_is_stable_for_same_evidence():
    seed_codeblocks_regression_sessions()
    service = DecisionService()
    decision_input = DecisionInput(application_fingerprint=CODEBLOCKS_FINGERPRINT)
    plan_a = service.plan_from_input(decision_input)
    plan_b = service.plan_from_input(decision_input)
    assert plan_a.plan_id == plan_b.plan_id
    assert plan_a.generated_at == plan_b.generated_at
