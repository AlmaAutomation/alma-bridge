"""Session lease contention tests."""

from __future__ import annotations

import time

import pytest

from alma_bridge.session.lease import SessionLeaseManager
from alma_bridge.storage import outcomes


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    outcomes.init_outcome_store()
    yield


def test_lease_contention_blocks_second_owner():
    sid = outcomes.new_session("/tmp/x.exe", None, {})
    a = SessionLeaseManager(owner_id="worker-a")
    b = SessionLeaseManager(owner_id="worker-b")
    assert a.acquire(sid, lease_sec=60).acquired is True
    assert b.acquire(sid, lease_sec=60).acquired is False


def test_lease_expiration_allows_reacquisition(monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.session_lease_sec", 1)
    sid = outcomes.new_session("/tmp/y.exe", None, {})
    a = SessionLeaseManager(owner_id="worker-a")
    b = SessionLeaseManager(owner_id="worker-b")
    assert a.acquire(sid, lease_sec=1).acquired is True
    time.sleep(2.0)
    assert b.acquire(sid, lease_sec=60).acquired is True
