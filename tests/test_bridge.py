from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from alma_bridge.execution.errors import detect_error_signature
from alma_bridge.hardware.shims import shims_for_indicators
from alma_bridge.learning.remediation import remediations_for_signature
from alma_bridge.main import create_app
from alma_bridge.storage.outcomes import init_outcome_store


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "outcomes.db")
    init_outcome_store()
    return TestClient(create_app())


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_hardware_profile(client):
    response = client.get("/hardware/profile")
    assert response.status_code == 200
    body = response.json()
    assert "profile" in body
    assert "capabilities" in body
    assert "shims_available" in body


def test_error_signature_detection():
    signature = detect_error_signature("failed to load dll msvcp140.dll", "")
    assert signature == "missing_dll"


def test_sudo_password_error_detection():
    stderr = (
        "sudo: a terminal is required to read the password; "
        "either use the -S option to read from standard input or configure an askpass helper\n"
        "sudo: a password is required\n"
    )
    assert detect_error_signature(stderr, "") == "sudo_password_required"


def test_remediations_for_gpu_crash():
    actions = remediations_for_signature("gpu_crash")
    ids = {action["id"] for action in actions}
    assert "software_rendering" in ids


def test_legacy_shims():
    shims = shims_for_indicators(["low_memory", "legacy_or_generic_gpu_driver"])
    ids = {shim["id"] for shim in shims}
    assert "old_cpu_compat" in ids
    assert "software_opengl" in ids


def test_bridge_plan_for_script(tmp_path, client):
    script = tmp_path / "hello.sh"
    script.write_text("#!/bin/sh\necho hello\n")
    script.chmod(0o755)

    response = client.post("/bridge/plan", json={"file_path": str(script)})
    assert response.status_code == 200
    body = response.json()
    plans = body["plans"]
    assert len(plans) >= 1
    assert "rank_source" in plans[0]
    assert "rank_position" in plans[0]
    assert "ranker" in body
    assert "model_loaded" in body["ranker"]


def test_bridge_sessions_recent(tmp_path, client):
    script = tmp_path / "runme.sh"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(0o755)
    client.post("/bridge/run", json={"file_path": str(script), "max_attempts": 2})

    response = client.get("/bridge/sessions/recent", params={"limit": 5})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 1
    assert body["sessions"][0]["file_path"] == str(script)

    filtered = client.get("/bridge/sessions/recent", params={"path": str(script)})
    assert filtered.status_code == 200
    assert filtered.json()["count"] >= 1


def test_prior_success_endpoint(tmp_path, client):
    script = tmp_path / "prior.sh"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(0o755)
    client.post("/bridge/run", json={"file_path": str(script), "max_attempts": 2})

    missing = client.get("/outcomes/prior-success", params={"path": str(tmp_path / "missing.sh")})
    assert missing.status_code == 200
    assert missing.json()["found"] is False

    found = client.get("/outcomes/prior-success", params={"path": str(script)})
    assert found.status_code == 200
    body = found.json()
    assert body["found"] is True
    assert body["strategy_id"]
    assert body["success_rate_for_path"] == 1.0


def test_bridge_sessions_include_attempt_metadata(tmp_path, client):
    script = tmp_path / "meta.sh"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(0o755)
    client.post("/bridge/run", json={"file_path": str(script), "max_attempts": 2})

    response = client.get("/bridge/sessions/recent", params={"limit": 5})
    session = response.json()["sessions"][0]
    assert session["attempt_count"] >= 1
    assert session["winning_strategy_id"]


def test_bridge_run_native_script(tmp_path, client):
    script = tmp_path / "runme.sh"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(0o755)

    response = client.post(
        "/bridge/run",
        json={"file_path": str(script), "sandbox": False, "max_attempts": 2},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["winning_attempt"] is not None
