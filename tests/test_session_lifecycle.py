"""Session lifecycle transition tests."""

from __future__ import annotations

import pytest

from alma_bridge.session.lifecycle import InvalidSessionTransition, SessionLifecycleManager
from alma_bridge.session.state import SessionState, validate_transition
from alma_bridge.storage import outcomes


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    outcomes.init_outcome_store()
    yield


def test_allowed_transition_created_to_inspecting():
    validate_transition(SessionState.CREATED, SessionState.INSPECTING)


def test_illegal_transition_succeeded_to_executing():
    with pytest.raises(ValueError):
        validate_transition(SessionState.SUCCEEDED, SessionState.EXECUTING)


def test_lifecycle_persists_transition():
    sid = outcomes.new_session("/tmp/a.exe", None, {})
    lifecycle = SessionLifecycleManager(sid)
    assert lifecycle.state == SessionState.CREATED
    lifecycle.transition(SessionState.INSPECTING, reason="test", expected_from=SessionState.CREATED)
    assert lifecycle.state == SessionState.INSPECTING
    rows = outcomes.list_session_transitions(sid)
    assert any(row["next_state"] == "INSPECTING" for row in rows)


def test_conflicting_transition_from_second_connection(tmp_path, monkeypatch):
    sid = outcomes.new_session("/tmp/b.exe", None, {})
    lifecycle_a = SessionLifecycleManager(sid)
    lifecycle_a.transition(SessionState.INSPECTING, reason="a", expected_from=SessionState.CREATED)

    lifecycle_b = SessionLifecycleManager(sid)
    assert lifecycle_b.state == SessionState.INSPECTING
    with pytest.raises(InvalidSessionTransition):
        lifecycle_b.transition(
            SessionState.PLANNING,
            reason="stale",
            expected_from=SessionState.CREATED,
        )


def test_awaiting_approval_is_non_terminal():
    validate_transition(SessionState.AWAITING_APPROVAL, SessionState.POLICY_CHECK)
    validate_transition(SessionState.AWAITING_APPROVAL, SessionState.FAILED)
