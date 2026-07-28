"""Tests for knowledge service and HTTP API."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from alma_bridge.knowledge.models import KNOWLEDGE_SCHEMA_VERSION, KnowledgeNotFoundError
from alma_bridge.knowledge.service import CompatibilityKnowledgeService
from alma_bridge.main import create_app
from alma_bridge.storage import outcomes
from tests.intelligence.conftest import CODEBLOCKS_FINGERPRINT
from tests.knowledge.conftest import seed_codeblocks_knowledge_sessions


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    outcomes.init_outcome_store()
    yield


def test_api_knowledge_endpoint_returns_profile():
    seed_codeblocks_knowledge_sessions()
    client = TestClient(create_app())
    response = client.get(f"/bridge/knowledge/applications/{CODEBLOCKS_FINGERPRINT}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == KNOWLEDGE_SCHEMA_VERSION
    assert payload["application_fingerprint"] == CODEBLOCKS_FINGERPRINT
    assert payload["total_sessions"] == 4
    assert payload["verified_successes"] == 2


def test_api_knowledge_endpoint_404_when_missing():
    client = TestClient(create_app())
    response = client.get("/bridge/knowledge/applications/unknown-fingerprint")
    assert response.status_code == 404


def test_knowledge_get_does_not_trigger_graph_ingestion():
    seed_codeblocks_knowledge_sessions()
    client = TestClient(create_app())
    with patch("alma_bridge.graph.ingestion.GraphIngestionEngine.ingest_application") as mocked:
        response = client.get(f"/bridge/knowledge/applications/{CODEBLOCKS_FINGERPRINT}")
        assert response.status_code == 200
        mocked.assert_not_called()


def test_service_profile_for_application_not_found():
    with pytest.raises(KnowledgeNotFoundError):
        CompatibilityKnowledgeService().profile_for_application("missing")
