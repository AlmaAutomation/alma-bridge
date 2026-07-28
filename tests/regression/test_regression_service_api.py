"""Tests for regression service and HTTP API."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from alma_bridge.knowledge.service import CompatibilityKnowledgeService
from alma_bridge.main import create_app
from alma_bridge.regression.models import REGRESSION_SCHEMA_VERSION, RegressionNotFoundError
from alma_bridge.regression.service import CompatibilityRegressionService
from alma_bridge.storage import outcomes
from tests.intelligence.conftest import CODEBLOCKS_FINGERPRINT
from tests.knowledge.conftest import KNOWLEDGE_SESSION_A, seed_codeblocks_knowledge_sessions
from tests.regression.conftest import (
    KNOWLEDGE_SESSION_C,
    KNOWLEDGE_SESSION_D,
    KNOWLEDGE_SESSION_E,
    seed_codeblocks_regression_sessions,
)


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    outcomes.init_outcome_store()
    yield


def test_api_regression_application_endpoint():
    seed_codeblocks_regression_sessions()
    client = TestClient(create_app())
    response = client.get(
        f"/bridge/regression/applications/{CODEBLOCKS_FINGERPRINT}",
        params={"session_id": KNOWLEDGE_SESSION_C},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == REGRESSION_SCHEMA_VERSION
    assert payload["comparison_session_id"] == KNOWLEDGE_SESSION_C
    assert payload["baseline_session_count"] == 4
    assert payload["current_session_count"] == 5
    assert payload["findings"]


def test_api_regression_session_endpoint():
    seed_codeblocks_regression_sessions()
    client = TestClient(create_app())
    response = client.get(f"/bridge/regression/sessions/{KNOWLEDGE_SESSION_C}")
    assert response.status_code == 200
    assert response.json()["comparison_session_id"] == KNOWLEDGE_SESSION_C


def test_api_regression_defaults_to_latest_session():
    seed_codeblocks_regression_sessions()
    client = TestClient(create_app())
    response = client.get(f"/bridge/regression/applications/{CODEBLOCKS_FINGERPRINT}")
    assert response.status_code == 200
    assert response.json()["comparison_session_id"] == KNOWLEDGE_SESSION_E


def test_first_session_has_no_findings():
    from tests.intelligence.conftest import sample_wine_gui_verification
    from tests.knowledge.conftest import _seed_session

    _seed_session(
        session_id=KNOWLEDGE_SESSION_A,
        verification=sample_wine_gui_verification(),
        finalize_success=True,
    )
    client = TestClient(create_app())
    response = client.get(
        f"/bridge/regression/applications/{CODEBLOCKS_FINGERPRINT}",
        params={"session_id": KNOWLEDGE_SESSION_A},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["baseline_session_count"] == 0
    assert payload["findings"] == []
    assert "Insufficient baseline" in payload["unchanged_summary"]


def test_api_regression_404_when_missing():
    client = TestClient(create_app())
    response = client.get("/bridge/regression/applications/unknown-fingerprint")
    assert response.status_code == 404


def test_regression_get_does_not_trigger_graph_ingestion():
    seed_codeblocks_regression_sessions()
    client = TestClient(create_app())
    with patch("alma_bridge.graph.ingestion.GraphIngestionEngine.ingest_application") as mocked:
        response = client.get(f"/bridge/regression/applications/{CODEBLOCKS_FINGERPRINT}")
        assert response.status_code == 200
        mocked.assert_not_called()


def test_strategy_rate_fixture_acceptance():
    seed_codeblocks_regression_sessions()
    report = CompatibilityRegressionService().report_for_application(
        CODEBLOCKS_FINGERPRINT,
        session_id=KNOWLEDGE_SESSION_C,
    )
    types = {item["regression_type"] for item in report.model_dump()["findings"]}
    assert "strategy_success_rate_dropped" in types


def test_exit_code_only_does_not_trigger_verified_regression():
    session_id = outcomes.new_session("/tmp/app.exe", "exit-only-hash", {})
    outcomes.record_attempt(
        session_id=session_id,
        attempt_number=1,
        strategy_id="native_host",
        remediation_id=None,
        runtime="native",
        command=["/tmp/app.exe"],
        env={},
        mode="host",
        success=True,
        exit_code=0,
        error_signature=None,
        detected_error=None,
        stdout="",
        stderr="",
        duration_ms=10,
        phase="native",
        verification={"passed": False, "confidence": 0.1, "checks": []},
    )
    outcomes.finalize_session(session_id, success=True, summary="exit only")

    profile = CompatibilityKnowledgeService().profile_for_application("exit-only-hash")
    assert profile.verified_successes == 0

    report = CompatibilityRegressionService().report_for_application(
        "exit-only-hash",
        session_id=session_id,
    )
    verified_types = [
        f.regression_type.value
        for f in report.findings
        if f.regression_type.value == "verified_success_to_verified_failure"
    ]
    assert verified_types == []


def test_application_isolation():
    seed_codeblocks_regression_sessions()
    other_id = outcomes.new_session("/tmp/other.exe", "other-fingerprint", {})
    outcomes.finalize_session(other_id, success=False, summary="other")
    report = CompatibilityRegressionService().report_for_application(CODEBLOCKS_FINGERPRINT)
    assert all(
        f.application_fingerprint == CODEBLOCKS_FINGERPRINT for f in report.findings
    )


def test_service_not_found():
    with pytest.raises(RegressionNotFoundError):
        CompatibilityRegressionService().report_for_application("missing")


def test_codeblocks_regression_acceptance_with_session_d():
    seed_codeblocks_regression_sessions()
    report = CompatibilityRegressionService().report_for_application(
        CODEBLOCKS_FINGERPRINT,
        session_id=KNOWLEDGE_SESSION_D,
    )
    assert report.comparison_session_id == KNOWLEDGE_SESSION_D
    assert report.findings
