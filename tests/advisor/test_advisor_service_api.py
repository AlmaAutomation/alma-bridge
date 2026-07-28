"""Advisor HTTP API and service integration tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from alma_bridge.advisor.models import ADVISOR_SCHEMA_VERSION
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


def test_api_advisor_application_endpoint():
    seed_codeblocks_regression_sessions()
    client = TestClient(create_app())
    response = client.get(
        f"/bridge/advisor/applications/{CODEBLOCKS_FINGERPRINT}",
        params={"session_id": KNOWLEDGE_SESSION_C},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == ADVISOR_SCHEMA_VERSION
    assert payload["observations"]
    assert payload["summary"]
    assert payload["limitations"]


def test_api_advisor_session_endpoint():
    seed_codeblocks_regression_sessions()
    client = TestClient(create_app())
    response = client.get(f"/bridge/advisor/sessions/{KNOWLEDGE_SESSION_C}")
    assert response.status_code == 200
    assert response.json()["application_fingerprint"] == CODEBLOCKS_FINGERPRINT


def test_api_advisor_404_when_missing():
    client = TestClient(create_app())
    response = client.get("/bridge/advisor/applications/unknown-fingerprint")
    assert response.status_code == 404


def test_advisor_get_does_not_trigger_graph_ingestion():
    seed_codeblocks_regression_sessions()
    client = TestClient(create_app())
    with patch("alma_bridge.graph.ingestion.GraphIngestionEngine.ingest_application") as mocked:
        response = client.get(f"/bridge/advisor/applications/{CODEBLOCKS_FINGERPRINT}")
        assert response.status_code == 200
        mocked.assert_not_called()


def test_advisor_get_performs_no_execution_mutation():
    seed_codeblocks_regression_sessions()
    client = TestClient(create_app())
    with patch("alma_bridge.storage.outcomes.record_attempt") as record_attempt:
        response = client.get(f"/bridge/advisor/applications/{CODEBLOCKS_FINGERPRINT}")
        assert response.status_code == 200
        record_attempt.assert_not_called()


def test_advisor_response_has_no_prescriptive_language():
    seed_codeblocks_regression_sessions()
    client = TestClient(create_app())
    payload = client.get(f"/bridge/advisor/applications/{CODEBLOCKS_FINGERPRINT}").json()
    serialized = str(payload).lower()
    for banned in ("best strategy", "requires vc++", "you should", "alma recommends"):
        assert banned not in serialized
