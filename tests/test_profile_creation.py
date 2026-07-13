from __future__ import annotations

import sqlite3
import threading

import pytest

from alma_bridge.compatibility.profile_creation import (
    ProfileCandidateService,
    ProfileCreationService,
    VerifiedAttemptInputs,
)
from alma_bridge.compatibility.profile_lineage import promote_candidate_snapshot
from alma_bridge.compatibility.profile_metrics import get_profile_counters, reset_profile_counters
from alma_bridge.compatibility.profile_store import _connect, ensure_profile_tables, init_profile_store
from alma_bridge.schemas.models import ExecutionMode
from alma_bridge.storage import outcomes
from tests.profile_test_helpers import (
    build_test_snapshot,
    sample_attempt_record,
    sample_hardware,
    sample_verification_payload,
)


@pytest.fixture
def profile_db(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profiles_enabled", True)
    monkeypatch.setattr(
        "alma_bridge.config.settings.compatibility_profile_creation_enabled", True
    )
    outcomes.init_outcome_store()
    reset_profile_counters()
    return db


def test_candidate_snapshot_persist_and_promote(profile_db):
    record = sample_attempt_record()
    inputs = VerifiedAttemptInputs(
        session_id="sess-1",
        file_path="/tmp/game.sh",
        executable_hash="deadbeef",
        hardware=sample_hardware(),
        record=record,
        verification_payload=sample_verification_payload(),
    )
    candidate_id = ProfileCandidateService.persist_from_verified(inputs)
    assert candidate_id

    profile_id = ProfileCreationService.promote(candidate_id)
    assert profile_id
    counters = get_profile_counters()
    assert counters.get("profile_candidate_persisted") == 1
    assert counters.get("profile_created") == 1


def test_candidate_persist_failure_does_not_raise(profile_db, monkeypatch):
    record = sample_attempt_record()
    inputs = VerifiedAttemptInputs(
        session_id="sess-fail",
        file_path="/tmp/game.sh",
        executable_hash="deadbeef",
        hardware=sample_hardware(),
        record=record,
        verification_payload=sample_verification_payload(),
    )

    def boom(_snapshot):
        raise RuntimeError("disk full")

    monkeypatch.setattr(
        "alma_bridge.compatibility.profile_creation.persist_candidate_snapshot",
        boom,
    )
    result = ProfileCandidateService.persist_from_verified(inputs)
    assert result is None
    assert get_profile_counters().get("profile_candidate_persist_failed") == 1

    with _connect() as conn:
        ensure_profile_tables(conn)
        row = conn.execute(
            """
            SELECT outcome FROM compatibility_profile_candidate_events
            WHERE session_id = ? ORDER BY created_at DESC LIMIT 1
            """,
            ("sess-fail",),
        ).fetchone()
    assert row["outcome"] == "persist_failed"


def test_repeated_retry_attaches_once(profile_db):
    snap = build_test_snapshot(session_id="retry-sess", attempt_number=3)
    promote_candidate_snapshot(snap)
    _, second = promote_candidate_snapshot(snap)
    _, third = promote_candidate_snapshot(snap)
    assert second == "attached"
    assert third == "attached"

    with _connect() as conn:
        ensure_profile_tables(conn)
        attachments = conn.execute(
            """
            SELECT COUNT(*) AS c FROM compatibility_profile_verification_attachments
            WHERE session_id = ? AND attempt_number = ?
            """,
            (snap.source_session_id, snap.source_attempt_number),
        ).fetchone()["c"]
        events = conn.execute(
            """
            SELECT COUNT(*) AS c FROM compatibility_profile_creation_events
            WHERE session_id = ? AND outcome = 'attached'
            """,
            (snap.source_session_id,),
        ).fetchone()["c"]
    assert attachments == 1
    assert events == 1


def test_concurrent_duplicate_creators_preserve_distinct_sessions(profile_db):
    snap_a = build_test_snapshot(session_id="concurrent-a", attempt_number=1)
    snap_b = build_test_snapshot(session_id="concurrent-b", attempt_number=1)
    assert snap_a.idempotency_key == snap_b.idempotency_key

    results: list[tuple[str, str]] = []
    lock = threading.Lock()

    def worker(snapshot):
        outcome = promote_candidate_snapshot(snapshot)
        with lock:
            results.append(outcome)

    threads = [
        threading.Thread(target=worker, args=(snap_a,)),
        threading.Thread(target=worker, args=(snap_b,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    profile_ids = {item[0] for item in results}
    assert len(profile_ids) == 1

    with _connect() as conn:
        ensure_profile_tables(conn)
        attachments = conn.execute(
            "SELECT session_id FROM compatibility_profile_verification_attachments ORDER BY session_id"
        ).fetchall()
    assert {row["session_id"] for row in attachments} == {"concurrent-a", "concurrent-b"}


def test_transaction_interruption_cannot_leave_orphan_rows(profile_db):
    """BEGIN IMMEDIATE + rollback leaves no profile header without child rows."""
    snap = build_test_snapshot(session_id="txn-sess")
    with _connect() as conn:
        ensure_profile_tables(conn)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            INSERT INTO compatibility_profiles (
                profile_id, lineage_key, profile_revision, idempotency_key, row_version,
                lifecycle_state, trust_state, schema_version, executable_hash, program_kind,
                architecture, product_version, host_compatibility_class_id, bridge_family_key,
                bridge_manifest_hash, verification_binding_key, strategy_id, policy_id,
                policy_version, aggregate_confidence, reuse_success_count, reuse_failure_count,
                source_session_id, source_attempt_number, candidate_id, verified_at,
                created_at, updated_at
            ) VALUES ('orphan-test', ?, 1, ?, 1, 'VERIFIED', 'locally_verified', 'v1',
                'hash', 'native_script', 'x86_64', NULL, ?, ?, ?, ?, 's', 'p', '1',
                0.0, 0, 0, ?, 1, ?, datetime('now'), datetime('now'), datetime('now'))
            """,
            (
                snap.profile_lineage_key,
                snap.idempotency_key,
                snap.host_compatibility_class_id,
                snap.bridge_family_key,
                snap.bridge_manifest_hash,
                snap.verification_binding_key,
                snap.source_session_id,
                snap.candidate_id,
            ),
        )
        try:
            conn.execute(
                "INSERT INTO compatibility_profile_program_fingerprints "
                "(profile_id, executable_hash, executable_format, architecture, program_kind, "
                "product_name, product_version, file_size, bundled_hashes_json, "
                "fingerprint_schema_version, program_identity_key, identity_json) "
                "VALUES ('orphan-test', 'h', 'script', 'x86_64', 'native_script', "
                "NULL, NULL, NULL, '{}', 'v1', 'k', '{}')"
            )
            raise sqlite3.OperationalError("interrupted")
        except sqlite3.OperationalError:
            conn.rollback()

    with _connect() as conn:
        ensure_profile_tables(conn)
        profile_count = conn.execute("SELECT COUNT(*) AS c FROM compatibility_profiles").fetchone()["c"]
        child_count = conn.execute(
            "SELECT COUNT(*) AS c FROM compatibility_profile_program_fingerprints"
        ).fetchone()["c"]
    assert profile_count == 0
    assert child_count == 0


def test_profile_creation_accepts_snapshot_not_request(profile_db):
    snap = build_test_snapshot(session_id="direct-snap")
    from alma_bridge.compatibility.profile_store import persist_candidate_snapshot

    persist_candidate_snapshot(snap)
    profile_id = ProfileCreationService.promote(snap)
    assert profile_id
