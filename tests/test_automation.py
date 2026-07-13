"""Tests for the automation platform (sessions, approval, runner, API)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from alma_bridge.automation.approval import consume_approval_token, create_approval_token
from alma_bridge.main import create_app
from alma_bridge.automation.playbooks import build_recipe_playbook, list_playbooks
from alma_bridge.automation.runner import machine_health, run_automation
from alma_bridge.automation.scanlite import scan_lite
from alma_bridge.automation.sessions import get_automation_session, init_automation_store
from alma_bridge.automation.verify import verify_modernization


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _fresh_automation_db(tmp_path, monkeypatch):
    db = tmp_path / "automation.db"
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    init_automation_store()
    yield


def test_scan_lite_missing_path():
    result = scan_lite("/nonexistent/path/for/alma-test")
    assert result["ok"] is False


def test_scan_lite_counts(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("world", encoding="utf-8")
    result = scan_lite(str(tmp_path))
    assert result["ok"] is True
    assert result["files_scanned"] >= 2


def test_playbook_recipes():
    playbooks = list_playbooks()
    ids = {p["id"] for p in playbooks}
    assert "school-lab" in ids
    assert "potato-browser-only" in ids
    assert "full-legacy-x86" in ids

    recipe = build_recipe_playbook("connectivity-only", os_release="ID=ubuntu")
    step_ids = {s["id"] for s in recipe["steps"]}
    assert "clock_sync" in step_ids
    assert "install_browser" not in step_ids


def test_school_lab_recipe():
    recipe = build_recipe_playbook("school-lab", os_release="ID=ubuntu\nID_LIKE=debian")
    step_ids = [s["id"] for s in recipe["steps"]]
    assert recipe["school_lab"] is True
    assert recipe.get("classroom_notes")
    assert "enable_multiarch" not in step_ids
    assert "school_classroom_checklist" in step_ids
    assert "school_lab_policy" in step_ids
    assert "clock_sync" in recipe["apply_step_ids"]
    if "write_browser_launcher" in step_ids:
        assert "school_desktop_shortcut" in recipe["apply_step_ids"]


def test_approval_token_lifecycle():
    created = create_approval_token(["clock_sync", "install_ca_bundle"], ttl_minutes=5)
    ok, err = consume_approval_token(created["token"], ["clock_sync"])
    assert ok is True
    assert err == ""
    ok2, err2 = consume_approval_token(created["token"])
    assert ok2 is False
    assert "already used" in err2


def test_approval_token_rejects_out_of_scope():
    created = create_approval_token(["clock_sync"], ttl_minutes=5)
    ok, err = consume_approval_token(created["token"], ["install_browser"])
    assert ok is False
    assert "not valid" in err


@patch("alma_bridge.automation.runner.assess_host")
def test_run_automation_plan_only(mock_assess):
    mock_assess.return_value = {
        "verdict": "needs_modernization",
        "potato_score": 40,
        "gaps": ["no_modern_browser"],
        "summary": "test",
        "browsers": {},
        "browser_recommendation": {},
        "hardware": {},
        "package_manager": "apt",
    }
    result = run_automation(apply=False)
    assert result["session_id"]
    assert result["success"] is True
    assert any(p["phase"] == "assess" for p in result["phases"])
    assert any(p["phase"] == "playbook" for p in result["phases"])

    session = get_automation_session(result["session_id"])
    assert session is not None
    assert session["success"] is True


@patch("alma_bridge.automation.runner.apply_playbook_steps")
@patch("alma_bridge.automation.runner.verify_modernization")
@patch("alma_bridge.automation.runner.assess_host")
def test_run_automation_apply_with_verify(mock_assess, mock_verify, mock_apply):
    assessment = {
        "verdict": "needs_modernization",
        "potato_score": 40,
        "gaps": ["no_modern_browser"],
        "summary": "test",
        "browsers": {},
        "browser_recommendation": {},
        "hardware": {},
        "package_manager": "apt",
    }
    mock_assess.return_value = assessment
    mock_apply.return_value = {
        "applied": True,
        "success": True,
        "results": [{"step_id": "clock_sync", "ok": True}],
    }
    mock_verify.return_value = {
        "verified": True,
        "after_assessment": {**assessment, "verdict": "mostly_ready", "potato_score": 60},
    }

    with patch("alma_bridge.automation.runner.prepare_sudo", return_value=(True, "")):
        result = run_automation(
            apply=True,
            allow_mutations=True,
            verify=True,
        )

    assert result["success"] is True
    assert any(p["phase"] == "apply" for p in result["phases"])
    assert any(p["phase"] == "verify" for p in result["phases"])


def test_verify_modernization_gap_diff():
    before = {"verdict": "needs_modernization", "potato_score": 30, "gaps": ["a", "b"]}
    after = {"verdict": "mostly_ready", "potato_score": 50, "gaps": ["b"], "browsers": {}}
    with patch("alma_bridge.automation.verify.assess_host", return_value=after):
        with patch("alma_bridge.automation.verify._probe_https", return_value={"ok": True}):
            result = verify_modernization(
                before=before,
                apply_results=[{"ok": True}],
            )
    assert result["gaps_closed"] == ["a"]
    assert result["verified"] is True


def test_machine_health_structure():
    health = machine_health()
    assert "hostname" in health
    assert "verdict" in health
    assert "recent_sessions" in health


def test_automation_api_health(client):
    resp = client.get("/automation/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "hostname" in body
    assert "verdict" in body


def test_automation_api_playbooks(client):
    resp = client.get("/automation/playbooks")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["playbooks"]) >= 4


def test_automation_api_recipe_preview(client):
    resp = client.get("/automation/playbooks/school-lab")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "school-lab"
    assert "clock_sync" in body["apply_step_ids"]

    resp404 = client.get("/automation/playbooks/not-a-recipe")
    assert resp404.status_code == 404


def test_flagship_program_api(client):
    resp = client.get("/flagship")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "alma-lab-modernization"
    assert "school-lab" in body["default_recipes"]["linux_lab"]

    root = client.get("/")
    assert root.json()["flagship_program"]["name"]


def test_playbooks_mark_flagship_recipes(client):
    resp = client.get("/automation/playbooks")
    playbooks = {p["id"]: p for p in resp.json()["playbooks"]}
    assert playbooks["school-lab"]["flagship"] is True
    assert playbooks["school-lab-windows"]["flagship"] is True
    assert playbooks.get("connectivity-only", {}).get("flagship") is not True


def test_automation_api_run_plan(client):
    resp = client.post("/automation/run", json={"apply": False})
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"]
    assert body["phases"]


def test_automation_api_approve(client):
    resp = client.post(
        "/automation/approve",
        json={"step_ids": ["clock_sync"], "ttl_minutes": 10},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"]
    assert body["step_ids"] == ["clock_sync"]


def test_automation_api_sessions(client):
    client.post("/automation/run", json={"apply": False})
    resp = client.get("/automation/sessions")
    assert resp.status_code == 200
    assert len(resp.json()["sessions"]) >= 1


def test_automation_api_agent_register(client):
    resp = client.post("/automation/agent/register", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["agent_id"]
    assert body["hostname"]
