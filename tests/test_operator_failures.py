"""Tests for operator failure examination and remediation."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from alma_bridge.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "outcomes.db")
    monkeypatch.setattr("alma_bridge.config.settings.api_key", None)
    monkeypatch.setattr("alma_bridge.config.settings.operator_enabled", False)
    monkeypatch.setattr("alma_bridge.config.settings.operator_autonomy", "autonomous")
    monkeypatch.setattr("alma_bridge.config.settings.operator_allow_mutations", True)
    monkeypatch.setattr("alma_bridge.config.settings.operator_max_risk", "medium")
    monkeypatch.setattr("alma_bridge.config.settings.operator_min_confidence", 0.7)
    from alma_bridge.automation.sessions import (
        finalize_automation_session,
        init_automation_store,
        new_automation_session,
    )
    from alma_bridge.storage.outcomes import init_outcome_store

    init_outcome_store()
    init_automation_store()
    with TestClient(create_app()) as c:
        yield c


def _seed_failed_exe_scan_session() -> str:
    from alma_bridge.automation.sessions import finalize_automation_session, new_automation_session

    session_id = new_automation_session(
        hostname="test-host",
        request={"scan_path": "/home/joshua/Games/ascension-setup-1.0.101.exe"},
    )
    finalize_automation_session(
        session_id,
        success=False,
        verdict="needs_work",
        potato_score=42,
        summary="Program run failed — Bridge never launched",
        phases=[
            {"phase": "assess", "ok": True, "data": {}},
            {"phase": "apply", "ok": False, "data": {"results": []}},
        ],
    )
    return session_id


def test_examine_failures_clears_superseded_sudo_errors(client):
    from alma_bridge.automation.sessions import finalize_automation_session, new_automation_session
    from alma_bridge.operator.failures import examine_failures

    failed_id = new_automation_session(hostname="test-host", request={})
    finalize_automation_session(
        failed_id,
        success=False,
        verdict="needs_work",
        potato_score=42,
        summary="apply failed before playbook",
        phases=[
            {"phase": "assess", "ok": True, "data": {}},
            {
                "phase": "apply",
                "ok": False,
                "error": "sudo: a password is required",
                "data": {"results": []},
            },
        ],
    )

    ok_id = new_automation_session(hostname="test-host", request={})
    finalize_automation_session(
        ok_id,
        success=True,
        verdict="ready",
        potato_score=85,
        summary="Automation finished — apply: ok",
        phases=[
            {"phase": "assess", "ok": True, "data": {}},
            {"phase": "apply", "ok": True, "data": {"results": []}},
        ],
    )

    exam = examine_failures(limit=5)
    assert exam["failure_count"] == 0
    assert exam["all_clear"] is True
    assert exam["resolved_sudo_failure_count"] == 1
    assert exam["failures"] == []


def test_examine_failures_proposes_bridge_for_exe_scan_path(client):
    _seed_failed_exe_scan_session()
    from alma_bridge.operator.failures import examine_failures

    exam = examine_failures(limit=5)
    assert exam["failure_count"] >= 1
    bridge = [m for m in exam["mitigations"] if m["kind"] == "bridge"]
    assert bridge, "expected Bridge mitigation for .exe in scan_path without bridge phase"
    assert "ascension-setup-1.0.101.exe" in bridge[0]["file_path"]
    assert bridge[0]["auto_eligible"] is True


def test_operator_failures_api(client):
    _seed_failed_exe_scan_session()
    resp = client.get("/operator/failures?limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["failure_count"] >= 1
    assert any(m["kind"] == "bridge" for m in body["mitigations"])


def test_operator_routes_api(client):
    _seed_failed_exe_scan_session()
    resp = client.get(
        "/operator/routes",
        params={"error_text": "permission_denied wine prefix", "limit": 5},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["route_count"] >= 1
    assert len(body["routes"]) <= 5


def test_operator_remediate_dry_run(client):
    _seed_failed_exe_scan_session()
    resp = client.post("/operator/remediate", json={"apply": False})
    assert resp.status_code == 200
    body = resp.json()
    assert body["examination"]["failure_count"] >= 1
    remediation = body["remediation"]
    assert remediation["can_mutate"] is False
    assert all(r.get("skipped") for r in remediation["results"])


def test_operator_remediate_applies_when_policy_allows(client):
    _seed_failed_exe_scan_session()
    fake_execution = {"success": True, "summary": "bridge ok"}
    fake_routes = {"success_count": 1, "winning_route": "bridge:test", "results": [{"success": True}]}

    with patch("alma_bridge.operator.routes.execute_best_routes", return_value=fake_routes):
        with patch("alma_bridge.automation.runner.run_automation", return_value=fake_execution):
            resp = client.post("/operator/remediate", json={"apply": True, "only_auto": True})
    assert resp.status_code == 200
    remediation = resp.json()["remediation"]
    assert remediation["applied"] is True
    assert remediation["success_count"] >= 1


def test_apply_all_applies_mitigations_within_risk_not_only_auto(client, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.operator_apply_all", True)
    from alma_bridge.operator.failures import apply_mitigations

    exam = {
        "mitigations": [
            {
                "id": "heal:low_conf",
                "kind": "heal",
                "title": "Low confidence heal",
                "error_text": "test error",
                "risk": "medium",
                "confidence": 0.55,
                "auto_eligible": False,
            },
            {
                "id": "retry:lab_step",
                "kind": "modernize_retry",
                "title": "Retry step",
                "step_ids": ["lab_step"],
                "risk": "medium",
                "confidence": 0.55,
                "auto_eligible": False,
            },
        ],
    }

    fake_execution = {"success": True, "executed_remediations": [{"ok": True}]}
    with patch("alma_bridge.operator.failures.run_autopilot", return_value=fake_execution):
        with patch("alma_bridge.automation.runner.run_automation", return_value=fake_execution):
            result = apply_mitigations(exam, apply=True, only_auto=False)

    applied_ids = [r["mitigation_id"] for r in result["results"] if not r.get("skipped")]
    assert "heal:low_conf" in applied_ids
    assert "retry:lab_step" in applied_ids


def test_run_cycle_apply_all_uses_all_step_ids(client, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.operator_autonomy", "autonomous")
    monkeypatch.setattr("alma_bridge.config.settings.operator_allow_mutations", True)
    monkeypatch.setattr("alma_bridge.config.settings.operator_apply_all", True)

    captured: dict = {}

    def fake_run_automation(**kwargs):
        captured.update(kwargs)
        return {"success": True, "summary": "ok"}

    with patch("alma_bridge.operator.brain.run_automation", side_effect=fake_run_automation):
        with patch("alma_bridge.operator.brain.apply_mitigations", return_value={"applied": False, "results": []}):
            resp = client.post("/operator/tick", json={"apply": True})

    assert resp.status_code == 200
    body = resp.json()
    assert body.get("apply_all") is True
    assert captured.get("step_ids") is not None


def test_run_cycle_includes_remediation(client, monkeypatch):
    _seed_failed_exe_scan_session()
    monkeypatch.setattr("alma_bridge.config.settings.operator_autonomy", "autonomous")
    monkeypatch.setattr("alma_bridge.config.settings.operator_allow_mutations", True)
    monkeypatch.setattr("alma_bridge.config.settings.operator_apply_all", True)

    fake_execution = {"success": True, "summary": "bridge ok"}
    fake_routes = {"success_count": 1, "winning_route": "bridge:test", "results": [{"success": True}]}
    with patch("alma_bridge.operator.routes.execute_best_routes", return_value=fake_routes):
        with patch("alma_bridge.automation.runner.run_automation", return_value=fake_execution):
            resp = client.post("/operator/tick", json={"apply": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["applied"] is True
    assert body["remediation"] is not None
    assert body["remediation"]["success_count"] >= 1
