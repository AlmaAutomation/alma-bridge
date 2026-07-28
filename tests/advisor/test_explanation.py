"""Deterministic advisor explanation engine tests."""

from __future__ import annotations

import copy

import pytest

from alma_bridge.advisor.context import AdvisorContextBuilder
from alma_bridge.advisor.explanation import DeterministicAdvisorEngine
from alma_bridge.advisor.policy import explanation_contains_forbidden_language
from alma_bridge.advisor.service import CompatibilityAdvisorService
from alma_bridge.storage import outcomes
from tests.intelligence.conftest import CODEBLOCKS_FINGERPRINT, sample_wine_gui_verification
from tests.knowledge.conftest import KNOWLEDGE_SESSION_A, _seed_session
from tests.regression.conftest import (
    KNOWLEDGE_SESSION_C,
    seed_codeblocks_regression_sessions,
)


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    outcomes.init_outcome_store()
    yield


def _explain(session_id=None):
    service = CompatibilityAdvisorService()
    return service.explain_for_application(
        CODEBLOCKS_FINGERPRINT,
        session_id=session_id,
    )


def test_every_observation_has_provenance():
    seed_codeblocks_regression_sessions()
    explanation = _explain(session_id=KNOWLEDGE_SESSION_C)
    assert explanation.observations
    for observation in explanation.observations:
        assert observation.evidence_references


def test_verified_success_history_uses_authoritative_verification_only():
    seed_codeblocks_regression_sessions()
    explanation = _explain()
    outcome_obs = [
        obs
        for obs in explanation.observations
        if obs.category.value == "verified_outcome_history"
    ]
    assert outcome_obs
    assert "authoritatively verified successful" in outcome_obs[0].statement.lower()


def test_exit_code_only_success_not_counted_as_verified():
    session_id = "exit-only-advisor-session"
    _seed_session(
        session_id=session_id,
        verification=None,
        finalize_success=True,
    )
    explanation = _explain(session_id=session_id)
    outcome_obs = [
        obs
        for obs in explanation.observations
        if obs.category.value == "verified_outcome_history"
    ]
    assert outcome_obs
    assert "authoritatively verified successful" not in outcome_obs[0].statement.lower()
    assert "unverifiable" in outcome_obs[0].statement.lower()


def test_strategy_history_is_descriptive_not_prescriptive():
    seed_codeblocks_regression_sessions()
    explanation = _explain()
    serialized = explanation.model_dump_json().lower()
    assert "best strategy" not in serialized
    assert "use wine_gui" not in serialized
    strategy_obs = [
        obs for obs in explanation.observations if obs.category.value == "strategy_history"
    ]
    assert strategy_obs
    assert "verified success rate" in strategy_obs[0].statement.lower()


def test_runtime_observations_never_become_required():
    seed_codeblocks_regression_sessions()
    explanation = _explain()
    serialized = explanation.model_dump_json().lower()
    assert "runtime_required" not in serialized
    assert "requires vc++" not in serialized
    assert any(
        "does not infer a runtime requirement" in limitation.lower()
        for limitation in explanation.limitations
    )


def test_framework_conflicts_preserve_all_sides():
    seed_codeblocks_regression_sessions()
    explanation = _explain()
    conflict_obs = [
        obs
        for obs in explanation.observations
        if obs.category.value == "conflicting_evidence"
    ]
    assert conflict_obs
    statement = conflict_obs[0].statement.lower()
    assert "wxwidgets" in statement or "wx" in statement
    assert "qt" in statement


def test_regression_explanation_cites_regression_layer():
    seed_codeblocks_regression_sessions()
    explanation = _explain(session_id=KNOWLEDGE_SESSION_C)
    change_obs = [
        obs
        for obs in explanation.observations
        if obs.category.value == "compatibility_change" and obs.severity == "critical"
    ]
    assert change_obs
    assert change_obs[0].source_layer.value == "regression"
    assert change_obs[0].evidence_references


def test_no_regression_result_is_factual():
    from tests.knowledge.conftest import seed_codeblocks_knowledge_sessions

    seed_codeblocks_knowledge_sessions()
    service = CompatibilityAdvisorService()
    explanation = service.explain_for_application(
        CODEBLOCKS_FINGERPRINT,
        session_id=KNOWLEDGE_SESSION_A,
    )
    assert explanation_contains_forbidden_language(explanation.summary) is False
    assert any(
        "insufficient" in item.lower() for item in explanation.limitations
    ) or any(
        obs.category.value == "compatibility_change"
        for obs in explanation.observations
    )


def test_sparse_evidence_produces_limitations():
    _seed_session(
        session_id=KNOWLEDGE_SESSION_A,
        verification=sample_wine_gui_verification(),
        finalize_success=True,
    )
    explanation = _explain(session_id=KNOWLEDGE_SESSION_A)
    assert any(
        "insufficient" in limitation.lower() for limitation in explanation.limitations
    )


def test_deterministic_output_except_generated_at():
    seed_codeblocks_regression_sessions()
    first = _explain(session_id=KNOWLEDGE_SESSION_C).model_dump()
    second = _explain(session_id=KNOWLEDGE_SESSION_C).model_dump()
    first.pop("generated_at")
    second.pop("generated_at")
    assert first == second


def test_forbidden_language_in_engine_fails_validation():
    seed_codeblocks_regression_sessions()
    builder = AdvisorContextBuilder()
    context = builder.build(CODEBLOCKS_FINGERPRINT, session_id=KNOWLEDGE_SESSION_C)
    engine = DeterministicAdvisorEngine()

    class BadEngine(DeterministicAdvisorEngine):
        def _build_summary(self, context, observations, limitations):
            return "Best strategy is wine_gui."

    with pytest.raises(Exception):
        BadEngine().explain(context)


def test_codeblocks_acceptance_explanation_content():
    seed_codeblocks_regression_sessions()
    explanation = _explain(session_id=KNOWLEDGE_SESSION_C)
    serialized = explanation.model_dump_json().lower()
    assert "wine_gui" in serialized
    assert "wxwidgets" in serialized or "wx" in serialized
    assert "qt" in serialized
    assert explanation_contains_forbidden_language(explanation.summary) is False
    assert "verified" in explanation.summary.lower()


def test_application_isolation():
    seed_codeblocks_regression_sessions()
    other_id = "other-advisor-app-session"
    _seed_session(
        session_id=other_id,
        fingerprint="other-fingerprint-advisor",
        file_path="/tmp/other.exe",
        verification=sample_wine_gui_verification(),
    )
    explanation = _explain()
    assert explanation.application_fingerprint == CODEBLOCKS_FINGERPRINT
    assert "other-fingerprint-advisor" not in explanation.model_dump_json()


def test_malformed_upstream_evidence_fails_closed(monkeypatch):
    seed_codeblocks_regression_sessions()

    def _broken(*args, **kwargs):
        from alma_bridge.knowledge.models import MalformedKnowledgeEvidenceError

        raise MalformedKnowledgeEvidenceError("broken", details=["bad"])

    monkeypatch.setattr(
        "alma_bridge.knowledge.service.CompatibilityKnowledgeService.profile_for_application",
        _broken,
    )
    service = CompatibilityAdvisorService()
    with pytest.raises(Exception):
        service.explain_for_application(CODEBLOCKS_FINGERPRINT)
