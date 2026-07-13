"""Regression tests for auto-compatibility route-loop lifecycle."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from alma_bridge.learning.orchestrator import BridgeOrchestrator
from alma_bridge.schemas.models import AttemptRecord, BridgeRequest, BridgeSessionResult, ExecutionMode
from alma_bridge.session.lifecycle import SessionLifecycleManager
from alma_bridge.session.services.routes import RouteExecutionResult
from alma_bridge.session.state import SessionState
from alma_bridge.storage import outcomes


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    outcomes.init_outcome_store()
    yield


def _failed_attempt() -> AttemptRecord:
    return AttemptRecord(
        attempt_number=1,
        strategy_id="native_host",
        runtime="native",
        command=["/bin/sh", "probe.sh"],
        mode=ExecutionMode.HOST,
        success=False,
        stderr="unrelated failure",
        error_signature="unknown_error",
    )


def _route_retry_result(route_id: str) -> RouteExecutionResult:
    return RouteExecutionResult(
        route_id=route_id,
        kind="heal_then_bridge",
        success=False,
        requires_bridge_retry=True,
    )


def _setup_lifecycle(session_id: str) -> SessionLifecycleManager:
    lifecycle = SessionLifecycleManager(session_id)
    lifecycle.transition(SessionState.CREATED, reason="test", expected_from=SessionState.CREATED)
    lifecycle.transition(SessionState.INSPECTING, reason="test", expected_from=SessionState.CREATED)
    lifecycle.transition(SessionState.PLANNING, reason="test", expected_from=SessionState.INSPECTING)
    lifecycle.transition(SessionState.POLICY_CHECK, reason="test", expected_from=SessionState.PLANNING)
    lifecycle.transition(SessionState.EXECUTING, reason="test", expected_from=SessionState.POLICY_CHECK)
    lifecycle.transition(SessionState.OBSERVING, reason="test", expected_from=SessionState.EXECUTING)
    lifecycle.transition(SessionState.CLASSIFYING, reason="test", expected_from=SessionState.OBSERVING)
    return lifecycle


@pytest.mark.parametrize("shadow_enabled", [False, True])
def test_second_route_uses_legal_lifecycle_after_failed_bridge_retry(monkeypatch, shadow_enabled):
    monkeypatch.setattr("alma_bridge.config.settings.bridge_auto_remediate", True)
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profile_shadow_mode", shadow_enabled)
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profiles_enabled", shadow_enabled)

    orchestrator = BridgeOrchestrator()
    session_id = outcomes.new_session("/tmp/probe.sh", "abc", {})
    lifecycle = _setup_lifecycle(session_id)
    attempts = [_failed_attempt()]

    routes = [
        {"id": "route:heal_then_bridge:probe.sh", "kind": "heal_then_bridge"},
        {"id": "route:baseline_retry", "kind": "baseline_retry"},
    ]
    route_results = [
        _route_retry_result("route:heal_then_bridge:probe.sh"),
        RouteExecutionResult(route_id="route:baseline_retry", kind="baseline_retry", success=True),
    ]
    call_count = {"n": 0}

    def fake_run_session(**kwargs):
        call_count["n"] += 1
        lc = kwargs["lifecycle"]
        if lc.state == SessionState.EXECUTING:
            lc.transition(SessionState.OBSERVING, reason="nested", expected_from=SessionState.EXECUTING)
            lc.transition(SessionState.CLASSIFYING, reason="nested", expected_from=SessionState.OBSERVING)
        return BridgeSessionResult(
            session_id=session_id,
            file_path="/tmp/probe.sh",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            success=False,
            summary="retry failed",
            attempts=attempts,
        )

    transitions_before = len(outcomes.list_session_transitions(session_id))

    with patch.object(orchestrator._route_discovery, "discover", return_value={"routes": routes}):
        with patch.object(orchestrator._route_selection, "select", return_value=routes):
            with patch.object(orchestrator._route_executor, "execute_route", side_effect=route_results):
                with patch.object(orchestrator, "_run_session", side_effect=fake_run_session):
                    result = orchestrator._try_auto_compatibility(
                        request=BridgeRequest(file_path="/tmp/probe.sh", max_attempts=1),
                        session_id=session_id,
                        lifecycle=lifecycle,
                        attempt_records=attempts,
                        hardware={},
                        started_at=datetime.now(timezone.utc),
                        digest="abc",
                        last_recommended=[],
                        rerank_events=[],
                    )

    assert call_count["n"] == 1
    assert result is None
    rows = outcomes.list_session_transitions(session_id)
    new_rows = rows[transitions_before:]
    chain = [(r["previous_state"], r["next_state"]) for r in new_rows]
    assert ("CLASSIFYING", "ESCALATING") in chain
    assert ("ESCALATING", "POLICY_CHECK") in chain
    assert ("CLASSIFYING", "RETRYING") in chain
    assert ("RETRYING", "POLICY_CHECK") in chain
    illegal = [t for t in new_rows if t["previous_state"] == "CLASSIFYING" and t["next_state"] == "EXECUTING"]
    assert not illegal


def test_three_consecutive_failed_bridge_retries_remain_legal(monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.bridge_auto_remediate", True)
    orchestrator = BridgeOrchestrator()
    session_id = outcomes.new_session("/tmp/a.exe", "abc", {})
    lifecycle = _setup_lifecycle(session_id)
    attempts = [_failed_attempt()]
    routes = [
        {"id": f"route:{i}", "kind": "heal_then_bridge"}
        for i in range(3)
    ]

    with patch.object(orchestrator._route_discovery, "discover", return_value={"routes": routes}):
        with patch.object(orchestrator._route_selection, "select", return_value=routes):
            with patch.object(
                orchestrator._route_executor,
                "execute_route",
                side_effect=[_route_retry_result(r["id"]) for r in routes],
            ):
                with patch.object(
                    orchestrator,
                    "_run_session",
                    side_effect=lambda **kw: BridgeSessionResult(
                        session_id=session_id,
                        file_path="/tmp/a.exe",
                        started_at=datetime.now(timezone.utc),
                        finished_at=datetime.now(timezone.utc),
                        success=False,
                        attempts=attempts,
                    ),
                ):
                    orchestrator._try_auto_compatibility(
                        request=BridgeRequest(file_path="/tmp/a.exe"),
                        session_id=session_id,
                        lifecycle=lifecycle,
                        attempt_records=attempts,
                        hardware={},
                        started_at=datetime.now(timezone.utc),
                        digest="abc",
                        last_recommended=[],
                        rerank_events=[],
                    )

    rows = outcomes.list_session_transitions(session_id)
    illegal = [r for r in rows if r["previous_state"] == "CLASSIFYING" and r["next_state"] == "EXECUTING"]
    assert not illegal


def test_route_success_after_one_failed_bridge_retry(monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.bridge_auto_remediate", True)
    orchestrator = BridgeOrchestrator()
    session_id = outcomes.new_session("/tmp/a.exe", "abc", {})
    lifecycle = _setup_lifecycle(session_id)
    attempts = [_failed_attempt()]
    routes = [
        {"id": "route:one", "kind": "heal_then_bridge"},
        {"id": "route:two", "kind": "heal_then_bridge"},
    ]
    winning = BridgeSessionResult(
        session_id=session_id,
        file_path="/tmp/a.exe",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        success=True,
        summary="ok",
        attempts=attempts,
        winning_attempt=attempts[0],
    )

    with patch.object(orchestrator._route_discovery, "discover", return_value={"routes": routes}):
        with patch.object(orchestrator._route_selection, "select", return_value=routes):
            with patch.object(
                orchestrator._route_executor,
                "execute_route",
                side_effect=[
                    _route_retry_result("route:one"),
                    _route_retry_result("route:two"),
                ],
            ):
                with patch.object(
                    orchestrator,
                    "_run_session",
                    side_effect=[BridgeSessionResult(
                        session_id=session_id,
                        file_path="/tmp/a.exe",
                        started_at=datetime.now(timezone.utc),
                        finished_at=datetime.now(timezone.utc),
                        success=False,
                        attempts=attempts,
                    ), winning],
                ):
                    result = orchestrator._try_auto_compatibility(
                        request=BridgeRequest(file_path="/tmp/a.exe"),
                        session_id=session_id,
                        lifecycle=lifecycle,
                        attempt_records=attempts,
                        hardware={},
                        started_at=datetime.now(timezone.utc),
                        digest="abc",
                        last_recommended=[],
                        rerank_events=[],
                    )

    assert result is not None
    assert result.success is True


def test_lifecycle_exception_records_shadow_actual(monkeypatch, tmp_path):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    outcomes.init_outcome_store()
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profiles_enabled", True)
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profile_shadow_mode", True)
    monkeypatch.setattr("alma_bridge.config.settings.bridge_auto_remediate", True)

    script = tmp_path / "probe.sh"
    script.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    script.chmod(0o755)

    orchestrator = BridgeOrchestrator()

    with patch.object(
        orchestrator,
        "_prepare_route_policy_check",
        side_effect=Exception("forced internal error"),
    ):
        result = orchestrator.run(BridgeRequest(file_path=str(script), max_attempts=1, auto_remediate=False))

    assert result.success is False
    import sqlite3

    conn = sqlite3.connect(db)
    count = conn.execute(
        "SELECT COUNT(*) FROM compatibility_profile_shadow_actual_outcomes WHERE session_id = ?",
        (result.session_id,),
    ).fetchone()[0]
    assert count >= 1
