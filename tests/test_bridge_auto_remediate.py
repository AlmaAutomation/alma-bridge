"""Bridge auto-compatibility lineage tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from alma_bridge.learning.orchestrator import BridgeOrchestrator, _failure_error_text
from alma_bridge.schemas.models import AttemptRecord, BridgeRequest, BridgeSessionResult, ExecutionMode
from alma_bridge.session.services.routes import RouteExecutionResult
from alma_bridge.storage import outcomes


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    outcomes.init_outcome_store()
    yield


def test_failure_error_text_collects_stderr_and_signatures():
    records = [
        AttemptRecord(
            attempt_number=1,
            strategy_id="wine",
            runtime="wine",
            command=["wine", "a.exe"],
            mode=ExecutionMode.HOST,
            success=False,
            stderr="err:0034: missing dll",
            error_signature="missing_dll",
        ),
    ]
    text = _failure_error_text(records)
    assert "missing dll" in text
    assert "missing_dll" in text


def test_escalation_preserves_session_lineage(monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.bridge_auto_remediate", True)
    monkeypatch.setattr("alma_bridge.config.settings.operator_allow_mutations", True)

    orchestrator = BridgeOrchestrator()
    request = BridgeRequest(file_path="/tmp/game.exe")
    attempts = [
        AttemptRecord(
            attempt_number=1,
            strategy_id="wine",
            runtime="wine",
            command=["wine", "game.exe"],
            mode=ExecutionMode.HOST,
            success=False,
            stderr="sidecar_silent_crash",
            error_signature="sidecar_silent_crash",
        )
    ]

    retry_session = BridgeSessionResult(
        session_id="parent-1",
        file_path="/tmp/game.exe",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        success=True,
        summary="retry ok",
        attempts=attempts,
    )

    route_result = RouteExecutionResult(
        route_id="route:wine_prefix_bootstrap:game.exe",
        kind="wine_prefix_bootstrap",
        success=False,
        requires_bridge_retry=True,
        prefix_fix={"actions": ["repair"]},
    )

    with patch.object(orchestrator._route_discovery, "discover", return_value={"routes": [{"id": "r1", "kind": "wine_prefix_bootstrap"}]}):
        with patch.object(orchestrator._route_selection, "select", return_value=[{"id": "r1", "kind": "wine_prefix_bootstrap"}]):
            with patch.object(orchestrator._route_executor, "execute_route", return_value=route_result):
                with patch.object(orchestrator, "_run_session", return_value=retry_session):
                    result = orchestrator._try_auto_compatibility(
                        request=request,
                        session_id="parent-1",
                        attempt_records=attempts,
                        hardware={},
                        started_at=datetime.now(timezone.utc),
                        digest="abc",
                        last_recommended=[],
                        rerank_events=[],
                    )

    assert result is not None
    assert result.success is True
    assert result.session_id == "parent-1"
    assert "Auto-compatibility succeeded" in result.summary

    sessions = outcomes.list_recent_sessions(limit=10)
    assert len(sessions) == 0 or all(s["session_id"] == "parent-1" for s in sessions if s.get("success"))


def test_try_auto_compatibility_disabled_when_flag_off(monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.bridge_auto_remediate", False)
    orchestrator = BridgeOrchestrator()
    request = BridgeRequest(file_path="/tmp/game.exe", auto_remediate=False)
    result = orchestrator._try_auto_compatibility(
        request=request,
        session_id="parent-1",
        attempt_records=[],
        hardware={},
        started_at=datetime.now(timezone.utc),
        digest=None,
        last_recommended=[],
        rerank_events=[],
    )
    assert result is None
