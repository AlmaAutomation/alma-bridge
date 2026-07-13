from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alma_bridge.main import create_app
from alma_bridge.storage.outcomes import init_outcome_store


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "outcomes.db")
    init_outcome_store()
    return TestClient(create_app())


def test_bridge_metrics_endpoint(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    body = response.text
    assert "alma_bridge_up 1" in body
    assert "alma_bridge_attempts_total" in body
    assert "alma_bridge_ranker_loaded" in body
