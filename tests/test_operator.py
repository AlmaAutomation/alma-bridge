"""Tests for the autonomous AI Operator (observe → decide → apply → verify)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alma_bridge.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "outcomes.db")
    monkeypatch.setattr("alma_bridge.config.settings.api_key", None)
    monkeypatch.setattr("alma_bridge.config.settings.operator_enabled", False)
    monkeypatch.setattr("alma_bridge.config.settings.operator_autonomy", "recommend")
    monkeypatch.setattr("alma_bridge.config.settings.operator_allow_mutations", False)
    from alma_bridge.automation.sessions import init_automation_store
    from alma_bridge.storage.outcomes import init_outcome_store

    init_outcome_store()
    init_automation_store()
    with TestClient(create_app()) as c:
        yield c


def test_observe_returns_system_and_ml_view(client):
    resp = client.get("/operator/observe")
    assert resp.status_code == 200
    body = resp.json()
    assert "verdict" in body
    assert "gaps" in body
    assert "ml" in body and "ranker_loaded" in body["ml"]
    # Internal keys must never leak to the API surface.
    assert not any(k.startswith("_") for k in body)


def test_plan_scores_actions_with_risk_and_confidence(client):
    resp = client.post("/operator/plan", json={})
    assert resp.status_code == 200
    plan = resp.json()["plan"]
    assert plan["autonomy"] == "recommend"
    for action in plan["actions"]:
        assert action["risk"] in ("low", "medium", "high")
        assert 0.0 <= action["confidence"] <= 1.0
        # In 'recommend' mode nothing is auto-eligible.
        assert action["auto_eligible"] is False
    assert plan["auto_apply_step_ids"] == []


def test_plan_healing_action_from_error_text(client):
    resp = client.post(
        "/operator/plan",
        json={"error_text": "error while loading shared libraries: libssl.so.1.0.0: cannot open shared object file"},
    )
    assert resp.status_code == 200
    plan = resp.json()["plan"]
    assert any(a["kind"] == "heal" for a in plan["actions"])


def test_tick_does_not_apply_in_recommend_mode(client):
    resp = client.post("/operator/tick", json={"apply": True})
    assert resp.status_code == 200
    body = resp.json()
    # recommend autonomy + no mutations policy → never applies.
    assert body["applied"] is False
    assert body["applied_step_ids"] == []


def test_autonomous_still_blocked_without_allow_mutations(client, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.operator_autonomy", "autonomous")
    monkeypatch.setattr("alma_bridge.config.settings.operator_allow_mutations", False)
    resp = client.post("/operator/tick", json={"apply": True})
    assert resp.status_code == 200
    assert resp.json()["applied"] is False


def test_start_blocked_when_operator_disabled(client):
    resp = client.post("/operator/start", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["started"] is False
    assert "operator_enabled" in body["reason"]


def test_status_reports_policy(client):
    resp = client.get("/operator/status")
    assert resp.status_code == 200
    status = resp.json()
    assert status["running"] is False
    assert status["config"]["autonomy"] == "recommend"
    assert status["config"]["allow_mutations"] is False
