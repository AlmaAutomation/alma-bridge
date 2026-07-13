"""Regression: ordinary /bridge/run tests must not inherit validation campaign .env."""

from __future__ import annotations

from unittest.mock import patch

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


def test_bridge_run_unaffected_when_runtime_env_has_campaign_mode(tmp_path, client):
    """Autouse conftest resets campaign settings so /bridge/run is not 403."""
    from alma_bridge.config import settings

    assert settings.validation_campaign_mode is False

    exe = tmp_path / "game.exe"
    exe.write_bytes(b"MZ")
    exe.chmod(0o755)

    def fake_execute(*, command, **kwargs):
        return {
            "success": False,
            "exit_code": 1,
            "error_signature": "permission_denied",
            "detected_error": "permission denied",
            "suggested_fix": "retry",
            "likely_causes": [],
            "stdout": "",
            "stderr": "permission denied",
            "duration_ms": 10,
        }

    with patch("alma_bridge.learning.orchestrator.execute_attempt", fake_execute):
        with patch(
            "alma_bridge.learning.orchestrator.fresh_prefix_path",
            lambda _sid: str(tmp_path / "prefix"),
        ):
            with patch("alma_bridge.hardware.prefixes.find_best_prefix", lambda _path: None):
                response = client.post(
                    "/bridge/run",
                    json={"file_path": str(exe), "sandbox": False, "max_attempts": 2},
                )

    assert response.status_code == 200, response.text
