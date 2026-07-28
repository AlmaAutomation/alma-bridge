"""Tests for optional advisor LLM renderer and API integration."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from alma_bridge.advisor.explanation import DeterministicAdvisorEngine
from alma_bridge.advisor.context import AdvisorContextBuilder
from alma_bridge.advisor.llm.provider import (
    ExceptionAdvisorLLMProvider,
    JsonAdvisorLLMProvider,
    TimeoutAdvisorLLMProvider,
)
from alma_bridge.advisor.llm.queries import evidence_ids_for_observation
from alma_bridge.advisor.llm.renderer import OptionalLLMRenderer
from alma_bridge.advisor.service import CompatibilityAdvisorService
from alma_bridge.main import create_app
from alma_bridge.storage import outcomes
from tests.intelligence.conftest import CODEBLOCKS_FINGERPRINT
from tests.regression.conftest import KNOWLEDGE_SESSION_C, seed_codeblocks_regression_sessions


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    monkeypatch.setattr("alma_bridge.config.settings.advisor_llm_enabled", False)
    outcomes.init_outcome_store()
    yield


def _deterministic_explanation():
    seed_codeblocks_regression_sessions()
    context = AdvisorContextBuilder().build(
        CODEBLOCKS_FINGERPRINT,
        session_id=KNOWLEDGE_SESSION_C,
    )
    return DeterministicAdvisorEngine().explain(context)


def _valid_llm_payload(deterministic):
    return {
        "summary": deterministic.summary.replace(
            "Alma does not infer",
            "Alma still does not infer",
        ),
        "observations": [
            {
                "observation_id": obs.observation_id,
                "statement": obs.statement,
                "evidence_reference_ids": evidence_ids_for_observation(obs),
            }
            for obs in deterministic.observations
        ],
        "limitations": list(deterministic.limitations),
    }


def test_deterministic_remains_default():
    seed_codeblocks_regression_sessions()
    client = TestClient(create_app())
    response = client.get(f"/bridge/advisor/applications/{CODEBLOCKS_FINGERPRINT}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["render_mode"] == "deterministic"
    assert payload["fallback_reason"] is None


def test_disabled_llm_does_not_call_provider():
    deterministic = _deterministic_explanation()
    provider = JsonAdvisorLLMProvider(_valid_llm_payload(deterministic))
    renderer = OptionalLLMRenderer(provider=provider, enabled=False)
    with patch.object(provider, "generate", wraps=provider.generate) as mocked:
        explanation, mode, reason = renderer.render(deterministic, mode="llm")
        mocked.assert_not_called()
    assert mode == "deterministic"
    assert reason is None


def test_valid_llm_rendering_accepted():
    deterministic = _deterministic_explanation()
    provider = JsonAdvisorLLMProvider(_valid_llm_payload(deterministic))
    renderer = OptionalLLMRenderer(provider=provider, enabled=True, timeout_seconds=2.0)
    explanation, mode, reason = renderer.render(deterministic, mode="llm")
    assert mode == "llm"
    assert reason is None
    assert "Alma still does not infer" in explanation.summary


def test_unknown_observation_id_falls_back():
    deterministic = _deterministic_explanation()
    payload = _valid_llm_payload(deterministic)
    payload["observations"].append(
        {
            "observation_id": "does-not-exist",
            "statement": "Invented.",
            "evidence_reference_ids": [],
        }
    )
    renderer = OptionalLLMRenderer(
        provider=JsonAdvisorLLMProvider(payload),
        enabled=True,
        timeout_seconds=2.0,
    )
    explanation, mode, reason = renderer.render(deterministic, mode="llm")
    assert mode == "deterministic_fallback"
    assert reason == "unknown_observation_id"
    assert explanation.summary == deterministic.summary


def test_recommendation_language_falls_back():
    deterministic = _deterministic_explanation()
    payload = _valid_llm_payload(deterministic)
    payload["summary"] = "Best strategy is wine_gui."
    renderer = OptionalLLMRenderer(
        provider=JsonAdvisorLLMProvider(payload),
        enabled=True,
        timeout_seconds=2.0,
    )
    _, mode, reason = renderer.render(deterministic, mode="llm")
    assert mode == "deterministic_fallback"
    assert reason == "policy_validation_failed"


def test_timeout_falls_back():
    deterministic = _deterministic_explanation()
    renderer = OptionalLLMRenderer(
        provider=TimeoutAdvisorLLMProvider(),
        enabled=True,
        timeout_seconds=0.01,
    )
    _, mode, reason = renderer.render(deterministic, mode="llm")
    assert mode == "deterministic_fallback"
    assert reason == "provider_timeout"


def test_malformed_json_falls_back():
    deterministic = _deterministic_explanation()

    class BadJsonProvider:
        def generate(self, request):
            raise json.JSONDecodeError("bad", "doc", 0)

    renderer = OptionalLLMRenderer(
        provider=BadJsonProvider(),
        enabled=True,
        timeout_seconds=2.0,
    )
    _, mode, reason = renderer.render(deterministic, mode="llm")
    assert mode == "deterministic_fallback"
    assert reason == "malformed_json"


def test_provider_exception_falls_back():
    deterministic = _deterministic_explanation()
    renderer = OptionalLLMRenderer(
        provider=ExceptionAdvisorLLMProvider(),
        enabled=True,
        timeout_seconds=2.0,
    )
    _, mode, reason = renderer.render(deterministic, mode="llm")
    assert mode == "deterministic_fallback"
    assert reason == "provider_error"


def test_api_llm_render_query_param():
    deterministic = _deterministic_explanation()
    service = CompatibilityAdvisorService(
        llm_provider=JsonAdvisorLLMProvider(_valid_llm_payload(deterministic)),
        llm_renderer=OptionalLLMRenderer(
            provider=JsonAdvisorLLMProvider(_valid_llm_payload(deterministic)),
            enabled=True,
            timeout_seconds=2.0,
        ),
    )
    with patch("alma_bridge.api.advisor_routes._service", service):
        client = TestClient(create_app())
        response = client.get(
            f"/bridge/advisor/applications/{CODEBLOCKS_FINGERPRINT}",
            params={"render": "llm", "session_id": KNOWLEDGE_SESSION_C},
        )
    assert response.status_code == 200
    assert response.json()["render_mode"] == "llm"


def test_api_success_during_provider_outage():
    seed_codeblocks_regression_sessions()
    service = CompatibilityAdvisorService(
        llm_renderer=OptionalLLMRenderer(
            provider=ExceptionAdvisorLLMProvider(),
            enabled=True,
            timeout_seconds=2.0,
        ),
    )
    with patch("alma_bridge.api.advisor_routes._service", service):
        client = TestClient(create_app())
        response = client.get(
            f"/bridge/advisor/applications/{CODEBLOCKS_FINGERPRINT}",
            params={"render": "llm"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["render_mode"] == "deterministic_fallback"
    assert payload["fallback_reason"] == "provider_error"


def test_deterministic_output_identical_when_llm_disabled():
    seed_codeblocks_regression_sessions()
    client = TestClient(create_app())
    baseline = client.get(
        f"/bridge/advisor/applications/{CODEBLOCKS_FINGERPRINT}",
        params={"render": "deterministic", "session_id": KNOWLEDGE_SESSION_C},
    ).json()
    attempted = client.get(
        f"/bridge/advisor/applications/{CODEBLOCKS_FINGERPRINT}",
        params={"render": "llm", "session_id": KNOWLEDGE_SESSION_C},
    ).json()
    assert attempted["render_mode"] == "deterministic"
    assert baseline["summary"] == attempted["summary"]
    assert baseline["observations"] == attempted["observations"]
