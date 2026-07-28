"""Recent sessions endpoint for Compatibility Explorer integration."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from alma_bridge.main import create_app
from alma_bridge.storage import outcomes


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    outcomes.init_outcome_store()
    return TestClient(create_app())


def _seed_session(
    *,
    session_id: str,
    file_path: str,
    file_hash: str | None,
    success: bool = True,
    session_state: str | None = "SUCCEEDED",
    verification: dict | None = None,
    started_at: str = "2026-07-28T10:00:00+00:00",
    finished_at: str = "2026-07-28T10:01:00+00:00",
) -> None:
    created = outcomes.new_session(file_path, file_hash or "", {})
    if created != session_id:
        with outcomes._connect() as conn:  # noqa: SLF001
            conn.execute(
                "UPDATE bridge_sessions SET session_id = ? WHERE session_id = ?",
                (session_id, created),
            )
            conn.execute(
                "UPDATE bridge_session_transitions SET session_id = ? WHERE session_id = ?",
                (session_id, created),
            )
            conn.commit()
    if session_state:
        with outcomes._connect() as conn:  # noqa: SLF001
            conn.execute(
                "UPDATE bridge_sessions SET session_state = ?, started_at = ?, finished_at = ? WHERE session_id = ?",
                (session_state, started_at, finished_at, session_id),
            )
            conn.commit()
    outcomes.record_attempt(
        session_id=session_id,
        attempt_number=1,
        strategy_id="wine_gui",
        remediation_id=None,
        runtime="wine",
        command=["wine", file_path],
        env={},
        mode="host_prefix",
        success=success,
        exit_code=0 if success else 1,
        error_signature=None,
        detected_error=None,
        stdout="",
        stderr="",
        duration_ms=100,
        phase="wine_gui",
        verification=verification,
    )
    outcomes.finalize_session(session_id, success=success, summary="test")


def test_recent_sessions_newest_first(client):
    _seed_session(
        session_id="older",
        file_path="/opt/old.exe",
        file_hash="hash-old",
        started_at="2026-07-28T09:00:00+00:00",
    )
    _seed_session(
        session_id="newer",
        file_path="/opt/new.exe",
        file_hash="hash-new",
        started_at="2026-07-28T11:00:00+00:00",
    )
    body = client.get("/bridge/sessions/recent", params={"limit": 10}).json()
    assert body["sessions"][0]["session_id"] == "newer"
    assert body["sessions"][1]["session_id"] == "older"


def test_recent_sessions_limit(client):
    for idx in range(5):
        _seed_session(
            session_id=f"sess-{idx}",
            file_path=f"/opt/app{idx}.exe",
            file_hash=f"hash-{idx}",
            started_at=f"2026-07-28T1{idx}:00:00+00:00",
        )
    body = client.get("/bridge/sessions/recent", params={"limit": 2}).json()
    assert body["count"] == 2
    assert len(body["sessions"]) == 2


def test_verified_true_only_with_authoritative_verification(client):
    _seed_session(
        session_id="verified-session",
        file_path="/opt/CodeBlocks/codeblocks.exe",
        file_hash="fp-verified",
        verification={
            "passed": True,
            "confidence": 0.95,
            "success_policy": {"policy_id": "wine_gui_process_v1", "policy_version": "1.1.0"},
            "checks": [],
            "evidence": ["process_survives"],
        },
    )
    item = client.get("/bridge/sessions/recent").json()["sessions"][0]
    assert item["verified"] is True


def test_succeeded_without_verification_is_not_verified(client):
    _seed_session(
        session_id="exit-only",
        file_path="/opt/app.exe",
        file_hash="fp-exit",
        session_state="SUCCEEDED",
        success=True,
        verification=None,
    )
    item = client.get("/bridge/sessions/recent").json()["sessions"][0]
    assert item["state"] == "SUCCEEDED"
    assert item["verified"] is False


def test_legacy_session_missing_fingerprint_is_graph_incompatible(client):
    _seed_session(
        session_id="legacy",
        file_path="/opt/legacy.exe",
        file_hash=None,
        verification={"passed": True, "confidence": 0.9, "checks": [], "evidence": []},
    )
    with outcomes._connect() as conn:  # noqa: SLF001
        conn.execute(
            "UPDATE bridge_sessions SET file_hash = NULL WHERE session_id = ?",
            ("legacy",),
        )
        conn.commit()
    item = client.get("/bridge/sessions/recent").json()["sessions"][0]
    assert item["application_fingerprint"] is None
    assert item["graph_compatible"] is False


def test_malformed_row_does_not_break_entire_response(client, monkeypatch):
    _seed_session(
        session_id="good",
        file_path="/opt/good.exe",
        file_hash="hash-good",
    )

    original = outcomes.list_recent_sessions

    def _with_bad_row(*, limit=20, file_path=None):
        rows = original(limit=limit, file_path=file_path)
        rows.insert(0, {"session_id": "bad"})
        return rows

    monkeypatch.setattr(outcomes, "list_recent_sessions", _with_bad_row)
    body = client.get("/bridge/sessions/recent").json()
    assert body["count"] == 1
    assert body["sessions"][0]["session_id"] == "good"


def test_recent_sessions_endpoint_is_read_only_get(client):
    assert client.post("/bridge/sessions/recent").status_code == 405
    assert client.put("/bridge/sessions/recent").status_code == 405
    assert client.delete("/bridge/sessions/recent").status_code == 405


def test_listing_recent_sessions_does_not_ingest_graph(client):
    _seed_session(
        session_id="graph-list",
        file_path="/opt/app.exe",
        file_hash="hash-graph",
    )
    with patch("alma_bridge.graph.ingestion.GraphIngestionEngine.ingest_session") as ingest:
        response = client.get("/bridge/sessions/recent")
        ingest.assert_not_called()
    assert response.status_code == 200
