"""Unit tests for stop-on-success authoritative verification helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from alma_bridge.learning.orchestrator import BridgeOrchestrator
from alma_bridge.schemas.models import AttemptRecord, BridgeRequest, ExecutionMode
from alma_bridge.session.lifecycle import SessionLifecycleManager
from alma_bridge.session.state import SessionState
from alma_bridge.session.stop_on_success_verification import (
    aggregate_verification_passed,
    attempt_row_authorizes_stop,
    in_memory_attempt_authorizes_stop,
    persisted_session_has_authoritative_verification,
)
from alma_bridge.session.verification_gateway import declare_verified_session_success
from alma_bridge.storage import outcomes


def _verification(*, passed: bool) -> dict:
    return {"passed": passed, "checks": [], "evidence": ["ok"]}


def _attempt_row(
    *,
    attempt_number: int = 1,
    success: bool,
    verification: object | None = None,
) -> dict:
    row = {
        "attempt_number": attempt_number,
        "strategy_id": "wine_host",
        "remediation_id": None,
        "runtime": "wine",
        "command": ["wine", "app.exe"],
        "mode": ExecutionMode.HOST.value,
        "success": success,
        "phase": "wine_gui",
    }
    if verification is not None:
        row["verification"] = verification
    return row


def _memory_attempt(*, success: bool) -> AttemptRecord:
    return AttemptRecord(
        attempt_number=1,
        strategy_id="wine_host",
        runtime="wine",
        command=["wine", "app.exe"],
        mode=ExecutionMode.HOST,
        success=success,
        phase="wine_gui",
    )


def test_authoritative_verification_only_on_persisted_attempt_row():
    persisted = {
        "success": 1,
        "attempts": [
            _attempt_row(success=False, verification=_verification(passed=True)),
            _attempt_row(success=True, verification=_verification(passed=True)),
        ],
    }
    assert persisted_session_has_authoritative_verification(None, persisted) is True


def test_succeeded_session_without_passed_verification_fails_closed():
    persisted = {
        "success": 1,
        "attempts": [
            _attempt_row(success=True, verification=_verification(passed=False)),
            _attempt_row(success=True),
        ],
        "winning_attempt": _attempt_row(success=True),
    }
    assert persisted_session_has_authoritative_verification(None, persisted) is False


def test_unsuccessful_attempt_with_passed_verification_does_not_authorize():
    row = _attempt_row(success=False, verification=_verification(passed=True))
    assert attempt_row_authorizes_stop(row) is False
    assert persisted_session_has_authoritative_verification(None, {"attempts": [row]}) is False


def test_successful_attempt_missing_verification_fails_closed():
    row = _attempt_row(success=True)
    assert attempt_row_authorizes_stop(row) is False


def test_successful_attempt_malformed_verification_fails_closed():
    row = _attempt_row(success=True, verification="shadow_prediction_only")
    assert attempt_row_authorizes_stop(row) is False
    assert aggregate_verification_passed(row) is False


def test_multiple_attempts_only_success_with_passed_authorizes():
    persisted = {
        "attempts": [
            _attempt_row(attempt_number=1, success=True, verification=_verification(passed=False)),
            _attempt_row(attempt_number=2, success=False, verification=_verification(passed=True)),
            _attempt_row(attempt_number=3, success=True, verification=_verification(passed=True)),
        ],
    }
    assert persisted_session_has_authoritative_verification(None, persisted) is True


def test_in_memory_and_persisted_rows_same_decision():
    row = _attempt_row(success=True, verification=_verification(passed=True))
    persisted = {"winning_attempt": row, "attempts": [row]}
    winning = _memory_attempt(success=True)
    assert in_memory_attempt_authorizes_stop(winning) is False
    assert persisted_session_has_authoritative_verification(winning, persisted) is True
    assert persisted_session_has_authoritative_verification(None, persisted) is True


def test_exit_code_or_route_success_without_verification_does_not_authorize():
    row = _attempt_row(success=True)
    row["exit_code"] = 0
    row["route_level_success"] = True
    assert attempt_row_authorizes_stop(row) is False


def test_shadow_prediction_payload_does_not_authorize():
    row = _attempt_row(
        success=True,
        verification={"passed": True, "source_type": "compatibility_profile_shadow"},
    )
    assert aggregate_verification_passed(row) is True
    row_shadow_only = _attempt_row(success=True, verification={"shadow_prediction": "would_win"})
    assert attempt_row_authorizes_stop(row_shadow_only) is False


def test_malformed_attempt_rows_fail_closed_without_raising():
    persisted = {
        "attempts": [
            None,
            "bad-row",
            _attempt_row(success=True, verification=_verification(passed=True)),
        ],
    }
    assert persisted_session_has_authoritative_verification(None, persisted) is True
    persisted_invalid = {"attempts": "not-a-list"}
    assert persisted_session_has_authoritative_verification(None, persisted_invalid) is False


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    outcomes.init_outcome_store()
    yield


def test_verification_persistence_failure_cannot_early_return_success():
    session_id = outcomes.new_session("/tmp/app.exe", "hash", {})
    lifecycle = SessionLifecycleManager(session_id)
    for state, prev in [
        (SessionState.CREATED, SessionState.CREATED),
        (SessionState.INSPECTING, SessionState.CREATED),
        (SessionState.PLANNING, SessionState.INSPECTING),
        (SessionState.POLICY_CHECK, SessionState.PLANNING),
        (SessionState.EXECUTING, SessionState.POLICY_CHECK),
        (SessionState.OBSERVING, SessionState.EXECUTING),
        (SessionState.VERIFYING, SessionState.OBSERVING),
    ]:
        lifecycle.transition(state, reason="test", expected_from=prev)
    declare_verified_session_success(
        lifecycle=lifecycle,
        session_id=session_id,
        transition=lambda lc, st, **kw: lc.transition(
            st, reason=kw.get("reason", "test"), expected_from=lc.state
        ),
        summary="verified ok",
    )
    outcomes.finalize_session(session_id, success=True, summary="verified ok")
    orchestrator = BridgeOrchestrator()
    result = orchestrator._return_if_session_succeeded(
        lifecycle=lifecycle,
        session_id=session_id,
        request=BridgeRequest(file_path="/tmp/app.exe"),
        started_at=datetime.now(timezone.utc),
        digest="hash",
        hardware={},
    )
    assert result is None


def test_early_return_requires_verification_on_current_session_attempts():
    session_id = outcomes.new_session("/tmp/app.exe", "hash", {})
    other_id = outcomes.new_session("/tmp/other.exe", "other", {})
    lifecycle = SessionLifecycleManager(session_id)
    for state, prev in [
        (SessionState.CREATED, SessionState.CREATED),
        (SessionState.INSPECTING, SessionState.CREATED),
        (SessionState.PLANNING, SessionState.INSPECTING),
        (SessionState.POLICY_CHECK, SessionState.PLANNING),
        (SessionState.EXECUTING, SessionState.POLICY_CHECK),
        (SessionState.OBSERVING, SessionState.EXECUTING),
        (SessionState.VERIFYING, SessionState.OBSERVING),
    ]:
        lifecycle.transition(state, reason="test", expected_from=prev)
    declare_verified_session_success(
        lifecycle=lifecycle,
        session_id=session_id,
        transition=lambda lc, st, **kw: lc.transition(
            st, reason=kw.get("reason", "test"), expected_from=lc.state
        ),
        summary="verified ok",
    )
    verified_row = _attempt_row(success=True, verification=_verification(passed=True))
    with patch.object(outcomes, "get_session") as get_session:
        get_session.side_effect = lambda sid: (
            {"success": 1, "attempts": [verified_row], "summary": "ok"}
            if sid == session_id
            else {"success": 1, "attempts": [verified_row], "summary": "other"}
            if sid == other_id
            else None
        )
        with patch.object(outcomes, "get_session_state") as get_state:
            get_state.return_value = SessionState.SUCCEEDED.value
            orchestrator = BridgeOrchestrator()
            assert (
                orchestrator._return_if_session_succeeded(
                    lifecycle=lifecycle,
                    session_id=session_id,
                    request=BridgeRequest(file_path="/tmp/app.exe"),
                    started_at=datetime.now(timezone.utc),
                    digest="hash",
                    hardware={},
                )
                is not None
            )
            other_lifecycle = SessionLifecycleManager(other_id)
            assert (
                orchestrator._return_if_session_succeeded(
                    lifecycle=other_lifecycle,
                    session_id=other_id,
                    request=BridgeRequest(file_path="/tmp/other.exe"),
                    started_at=datetime.now(timezone.utc),
                    digest="other",
                    hardware={},
                )
                is not None
            )
