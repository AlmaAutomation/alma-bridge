"""Commercial compliance API and data handling tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alma_bridge.compliance.program import redact_request_payload
from alma_bridge.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "outcomes.db")
    monkeypatch.setattr("alma_bridge.config.settings.api_key", None)
    from alma_bridge.automation.sessions import init_automation_store

    init_automation_store()
    with TestClient(create_app()) as c:
        yield c


def test_redact_request_payload():
    clean = redact_request_payload(
        {"apply": True, "sudo_password": "secret", "nested": {"approval_token": "tok"}}
    )
    assert clean["sudo_password"] == "[REDACTED]"
    assert clean["nested"]["approval_token"] == "[REDACTED]"
    assert clean["apply"] is True


def test_compliance_program_api(client):
    resp = client.get("/compliance/program")
    assert resp.status_code == 200
    body = resp.json()
    assert body["program_id"] == "alma-lab-modernization"
    assert body["commercial_ready"] is True
    assert body["data_practices"]["student_pii_collected"] is False
    assert len(body["legal_documents"]) >= 8
    assert any(d["id"] == "dpa" for d in body["legal_documents"])


def test_data_practices_api(client):
    resp = client.get("/compliance/program/data-practices")
    assert resp.status_code == 200
    assert resp.json()["retention_days_default"] == 365


def test_purge_data_api(client):
    from alma_bridge.automation.sessions import new_automation_session

    new_automation_session(hostname="test", request={"apply": False})
    resp = client.delete("/compliance/program/data", params={"older_than_days": 0})
    assert resp.status_code == 200
    assert resp.json()["purged_sessions"] >= 1
