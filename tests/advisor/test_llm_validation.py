"""Tests for bounded advisor LLM validation."""

from __future__ import annotations

import pytest

from alma_bridge.advisor.explanation import DeterministicAdvisorEngine
from alma_bridge.advisor.context import AdvisorContextBuilder
from alma_bridge.advisor.llm.models import RenderedAdvisorExplanation, RenderedObservation
from alma_bridge.advisor.llm.queries import build_llm_request, evidence_ids_for_observation
from alma_bridge.advisor.llm.validation import AdvisorOutputValidator, AdvisorValidationError
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


def _deterministic_explanation():
    seed_codeblocks_regression_sessions()
    context = AdvisorContextBuilder().build(
        CODEBLOCKS_FINGERPRINT,
        session_id=KNOWLEDGE_SESSION_C,
    )
    return DeterministicAdvisorEngine().explain(context)


def _valid_rendered(deterministic) -> RenderedAdvisorExplanation:
    return RenderedAdvisorExplanation(
        summary=deterministic.summary.replace(
            "Alma does not infer",
            "Alma still does not infer",
        ),
        observations=[
            RenderedObservation(
                observation_id=obs.observation_id,
                statement=obs.statement,
                evidence_reference_ids=evidence_ids_for_observation(obs),
            )
            for obs in deterministic.observations
        ],
        limitations=list(deterministic.limitations),
    )


def test_valid_llm_rendering_accepted():
    deterministic = _deterministic_explanation()
    rendered = _valid_rendered(deterministic)
    validated = AdvisorOutputValidator().validate(deterministic, rendered)
    assert validated.summary != deterministic.summary


def test_unknown_observation_id_rejected():
    deterministic = _deterministic_explanation()
    rendered = _valid_rendered(deterministic)
    rendered.observations.append(
        RenderedObservation(
            observation_id="unknown-id",
            statement="Invented observation.",
            evidence_reference_ids=["attempt:a:1"],
        )
    )
    with pytest.raises(AdvisorValidationError, match="unknown_observation_id"):
        AdvisorOutputValidator().validate(deterministic, rendered)


def test_missing_observation_id_rejected():
    deterministic = _deterministic_explanation()
    rendered = _valid_rendered(deterministic)
    rendered.observations = rendered.observations[:-1]
    with pytest.raises(AdvisorValidationError, match="missing_observation_id"):
        AdvisorOutputValidator().validate(deterministic, rendered)


def test_invented_framework_claim_rejected():
    deterministic = _deterministic_explanation()
    rendered = _valid_rendered(deterministic)
    rendered.observations[0].statement = "Electron framework was observed in all sessions."
    with pytest.raises(AdvisorValidationError, match="policy_validation_failed"):
        AdvisorOutputValidator().validate(deterministic, rendered)


def test_runtime_requirement_rejected():
    deterministic = _deterministic_explanation()
    rendered = _valid_rendered(deterministic)
    rendered.summary = (
        deterministic.summary + " This application has a runtime requirement for VC++."
    )
    with pytest.raises(AdvisorValidationError, match="policy_validation_failed"):
        AdvisorOutputValidator().validate(deterministic, rendered)


def test_recommendation_language_rejected():
    deterministic = _deterministic_explanation()
    rendered = _valid_rendered(deterministic)
    rendered.summary = "Best strategy is wine_gui for this application."
    with pytest.raises(AdvisorValidationError, match="policy_validation_failed"):
        AdvisorOutputValidator().validate(deterministic, rendered)


def test_missing_provenance_rejected():
    deterministic = _deterministic_explanation()
    rendered = _valid_rendered(deterministic)
    rendered.observations[0].evidence_reference_ids = []
    with pytest.raises(AdvisorValidationError, match="policy_validation_failed"):
        AdvisorOutputValidator().validate(deterministic, rendered)


def test_verification_status_cannot_be_changed():
    deterministic = _deterministic_explanation()
    rendered = _valid_rendered(deterministic)
    failure_obs = next(
        obs
        for obs in deterministic.observations
        if "verified failure" in obs.statement.lower()
        or "authoritative verified failure" in obs.statement.lower()
    )
    rendered_by_id = {obs.observation_id: obs for obs in rendered.observations}
    rendered_by_id[failure_obs.observation_id].statement = (
        "All sessions completed without issue."
    )
    with pytest.raises(AdvisorValidationError, match="policy_validation_failed"):
        AdvisorOutputValidator().validate(deterministic, rendered)


def test_build_llm_request_contains_policy_constraints():
    deterministic = _deterministic_explanation()
    request = build_llm_request(deterministic)
    assert request.application_name
    assert request.observations
    assert request.policy_constraints
