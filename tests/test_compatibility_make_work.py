"""Tests for the make-work compatibility endpoint."""

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
    monkeypatch.setattr("alma_bridge.config.settings.operator_allow_mutations", True)
    with TestClient(create_app()) as c:
        yield c


def test_make_work_dry_run(client):
    discovery = {
        "route_count": 2,
        "primary_signature": "permission_denied",
        "routes": [
            {"id": "a", "kind": "pathway", "title": "Fresh prefix", "score": 0.9},
        ],
    }
    execution = {"success_count": 0, "winning_route": None, "results": []}

    with patch("alma_bridge.operator.routes.discover_routes", return_value=discovery):
        with patch("alma_bridge.operator.routes.execute_best_routes", return_value=execution):
            resp = client.post(
                "/compatibility/make-work",
                json={"file_path": "/tmp/test.exe", "error_text": "permission_denied", "apply": False},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["route_count"] == 2
    assert body["success"] is False
    assert len(body["top_routes"]) == 1


def test_make_work_reports_success(client, tmp_path):
    discovery = {"route_count": 1, "routes": [{"id": "win", "title": "Bridge", "score": 0.95}]}
    from datetime import datetime, timezone

    from alma_bridge.schemas.models import BridgeSessionResult

    session = BridgeSessionResult(
        session_id="sess-1",
        file_path=str(tmp_path / "game.exe"),
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        success=True,
        summary="ok",
    )
    (tmp_path / "game.exe").write_bytes(b"MZ")

    with patch("alma_bridge.operator.routes.discover_routes", return_value=discovery):
        with patch("alma_bridge.api.routes.orchestrator.run", return_value=session):
            resp = client.post(
                "/compatibility/make-work",
                json={"file_path": str(tmp_path / "game.exe"), "error_text": "libssl missing", "apply": True},
            )

    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert resp.json()["winning_route"] == "bridge:orchestrator"
