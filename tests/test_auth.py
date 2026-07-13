"""API key middleware tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alma_bridge.main import create_app


@pytest.fixture()
def client_no_key(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "outcomes.db")
    monkeypatch.setattr("alma_bridge.config.settings.api_key", None)
    from alma_bridge.automation.sessions import init_automation_store

    init_automation_store()
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture()
def client_with_key(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "outcomes.db")
    monkeypatch.setattr("alma_bridge.config.settings.api_key", "test-secret-key")
    from alma_bridge.automation.sessions import init_automation_store

    init_automation_store()
    with TestClient(create_app()) as c:
        yield c


def test_health_open_with_api_key_configured(client_with_key):
    resp = client_with_key.get("/health")
    assert resp.status_code == 200


def test_assess_open_with_api_key_configured(client_with_key):
    resp = client_with_key.get("/modernization/assess")
    assert resp.status_code == 200
    body = resp.json()
    assert "lab_readiness_score" in body
    assert body["lab_readiness_score"] == body["potato_score"]


def test_protected_mutation_rejects_without_key(client_with_key):
    resp = client_with_key.post(
        "/automation/approve",
        json={"step_ids": ["clock_sync"], "ttl_minutes": 5},
    )
    assert resp.status_code == 401


def test_protected_mutation_accepts_key_header(client_with_key):
    resp = client_with_key.post(
        "/automation/approve",
        json={"step_ids": ["clock_sync"], "ttl_minutes": 5},
        headers={"X-API-Key": "test-secret-key"},
    )
    assert resp.status_code == 200
    assert resp.json()["token"]


def test_protected_mutation_open_when_key_unset(client_no_key):
    resp = client_no_key.post(
        "/automation/approve",
        json={"step_ids": ["clock_sync"], "ttl_minutes": 5},
    )
    assert resp.status_code == 200
