"""Ask Alma service, API, and acceptance tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from alma_bridge.ask.answer import JsonAskLLMProvider, OptionalLLMAnswerRenderer
from alma_bridge.ask.models import AskAlmaQuestion, QuestionType
from alma_bridge.ask.service import AskAlmaService
from alma_bridge.main import create_app
from alma_bridge.storage import outcomes
from tests.intelligence.conftest import CODEBLOCKS_FINGERPRINT, sample_wine_gui_verification
from tests.knowledge.conftest import KNOWLEDGE_SESSION_A, _seed_session
from tests.regression.conftest import KNOWLEDGE_SESSION_C, seed_codeblocks_regression_sessions


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    monkeypatch.setattr("alma_bridge.config.settings.advisor_llm_enabled", False)
    outcomes.init_outcome_store()
    yield


def _ask(question: str, *, session_id=None, render="deterministic"):
    service = AskAlmaService()
    return service.ask(
        AskAlmaQuestion(
            question=question,
            application_fingerprint=CODEBLOCKS_FINGERPRINT,
            session_id=session_id,
            render=render,
        )
    )


def test_answer_has_provenance():
    seed_codeblocks_regression_sessions()
    answer = _ask("Has wine_gui worked before?")
    assert answer.evidence_references
    assert answer.question_type == QuestionType.LAUNCH_STRATEGY_HISTORY


def test_verification_history_uses_authoritative_verification_only():
    seed_codeblocks_regression_sessions()
    answer = _ask("Has this application worked before?")
    assert "authoritatively verified" in answer.answer.lower()


def test_exit_code_only_not_described_as_verified():
    _seed_session(
        session_id=KNOWLEDGE_SESSION_A,
        verification=None,
        finalize_success=True,
    )
    answer = _ask("Has this application worked before?")
    assert "authoritatively verified successful" not in answer.answer.lower()


def test_framework_conflicts_preserved():
    seed_codeblocks_regression_sessions()
    answer = _ask("Show conflicting evidence.")
    assert "conflicting" in answer.answer.lower()
    assert "wxwidgets" in answer.answer.lower() or "qt" in answer.answer.lower()


def test_runtime_observation_never_becomes_requirement():
    seed_codeblocks_regression_sessions()
    answer = _ask("What runtimes were observed?")
    assert "requires" not in answer.answer.lower()
    assert any("does not infer" in item.lower() for item in answer.limitations)


def test_strategy_history_descriptive():
    seed_codeblocks_regression_sessions()
    answer = _ask("Has wine_gui worked before?")
    assert "best strategy" not in answer.answer.lower()
    assert "verified success" in answer.answer.lower()


def test_regression_answer_includes_evidence():
    seed_codeblocks_regression_sessions()
    answer = _ask("What changed in the latest session?", session_id=KNOWLEDGE_SESSION_C)
    assert answer.evidence_references
    assert answer.question_type == QuestionType.REGRESSION_CHANGES


def test_remediation_request_refused():
    seed_codeblocks_regression_sessions()
    answer = _ask("Should I install VC++?")
    assert answer.question_type == QuestionType.REMEDIATION_REFUSAL
    assert "read-only" in answer.answer.lower()
    assert "does not infer installation" in answer.answer.lower()


def test_unsupported_question_graceful():
    answer = _ask("What is the meaning of life?")
    assert answer.question_type == QuestionType.UNSUPPORTED
    assert "not supported" in answer.answer.lower()


def test_api_post_ask():
    seed_codeblocks_regression_sessions()
    client = TestClient(create_app())
    response = client.post(
        "/bridge/ask",
        json={
            "question": "Has wine_gui worked before?",
            "application_fingerprint": CODEBLOCKS_FINGERPRINT,
            "render": "deterministic",
        },
    )
    assert response.status_code == 200
    assert response.json()["evidence_references"]


def test_no_graph_ingestion_on_ask():
    seed_codeblocks_regression_sessions()
    client = TestClient(create_app())
    with patch("alma_bridge.graph.ingestion.GraphIngestionEngine.ingest_application") as mocked:
        response = client.post(
            "/bridge/ask",
            json={
                "question": "Has wine_gui worked before?",
                "application_fingerprint": CODEBLOCKS_FINGERPRINT,
            },
        )
        assert response.status_code == 200
        mocked.assert_not_called()


def test_no_execution_mutation_on_ask():
    seed_codeblocks_regression_sessions()
    client = TestClient(create_app())
    with patch("alma_bridge.storage.outcomes.record_attempt") as mocked:
        response = client.post(
            "/bridge/ask",
            json={
                "question": "Has wine_gui worked before?",
                "application_fingerprint": CODEBLOCKS_FINGERPRINT,
            },
        )
        assert response.status_code == 200
        mocked.assert_not_called()


def test_application_isolation():
    seed_codeblocks_regression_sessions()
    _seed_session(
        session_id="other-ask-session",
        fingerprint="other-fingerprint",
        file_path="/tmp/other.exe",
        verification=sample_wine_gui_verification(),
    )
    answer = _ask("Has wine_gui worked before?")
    assert "other-fingerprint" not in answer.model_dump_json()
    assert "other.exe" not in answer.answer.lower()


def test_session_scoped_regression_question():
    seed_codeblocks_regression_sessions()
    answer = _ask("What changed in the latest session?", session_id=KNOWLEDGE_SESSION_C)
    assert answer.evidence_references


def test_llm_failure_falls_back():
    seed_codeblocks_regression_sessions()
    deterministic = _ask("Has wine_gui worked before?")
    service = AskAlmaService(
        llm_renderer=OptionalLLMAnswerRenderer(
            provider=JsonAskLLMProvider("Best strategy is wine_gui."),
            enabled=True,
            timeout_seconds=2.0,
        )
    )
    answer = service.ask(
        AskAlmaQuestion(
            question="Has wine_gui worked before?",
            application_fingerprint=CODEBLOCKS_FINGERPRINT,
            render="llm",
        )
    )
    assert answer.render_mode == "deterministic_fallback"
    assert answer.answer == deterministic.answer


def test_valid_llm_rendering():
    seed_codeblocks_regression_sessions()
    deterministic = _ask("Has wine_gui worked before?")
    rewritten = deterministic.answer.replace("Yes.", "Yes —")
    service = AskAlmaService(
        llm_renderer=OptionalLLMAnswerRenderer(
            provider=JsonAskLLMProvider(rewritten),
            enabled=True,
            timeout_seconds=2.0,
        )
    )
    answer = service.ask(
        AskAlmaQuestion(
            question="Has wine_gui worked before?",
            application_fingerprint=CODEBLOCKS_FINGERPRINT,
            render="llm",
        )
    )
    assert answer.render_mode == "llm"
    assert answer.answer.startswith("Yes —")


def test_codeblocks_acceptance_flow():
    seed_codeblocks_regression_sessions()
    worked = _ask("Has wine_gui worked before?")
    assert worked.evidence_references
    assert "verified success" in worked.answer.lower()

    changed = _ask("What changed in the latest session?", session_id=KNOWLEDGE_SESSION_C)
    assert changed.evidence_references

    install = _ask("Should I install VC++?")
    assert "does not infer installation" in install.answer.lower()
