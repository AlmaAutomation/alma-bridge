from __future__ import annotations

from alma_bridge.compatibility.profile_fingerprints import build_bridge_manifest_hash
from alma_bridge.compatibility.profile_lineage import promote_candidate_snapshot
from alma_bridge.storage import outcomes
from tests.profile_test_helpers import build_test_snapshot


def _init_db(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "outcomes.db")
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profiles_enabled", True)
    monkeypatch.setattr(
        "alma_bridge.config.settings.compatibility_profile_creation_enabled", True
    )
    outcomes.init_outcome_store()


def test_idempotency_key_uniqueness_per_manifest(tmp_path, monkeypatch):
    _init_db(tmp_path, monkeypatch)
    snap_a = build_test_snapshot(env={"STABLE": "1"})
    snap_b = build_test_snapshot(env={"STABLE": "2"})
    assert snap_a.idempotency_key != snap_b.idempotency_key


def test_same_idempotency_key_single_profile_row(tmp_path, monkeypatch):
    _init_db(tmp_path, monkeypatch)
    first = build_test_snapshot(session_id="one")
    second = build_test_snapshot(session_id="two")
    assert first.idempotency_key == second.idempotency_key

    pid1, out1 = promote_candidate_snapshot(first)
    pid2, out2 = promote_candidate_snapshot(second)
    assert out1 == "created"
    assert out2 == "attached"
    assert pid1 == pid2

    from alma_bridge.compatibility.profile_store import _connect, ensure_profile_tables

    with _connect() as conn:
        ensure_profile_tables(conn)
        rows = conn.execute(
            "SELECT profile_revision FROM compatibility_profiles WHERE idempotency_key = ?",
            (first.idempotency_key,),
        ).fetchall()
    assert len(rows) == 1
    assert int(rows[0]["profile_revision"]) == 1


def test_manifest_hash_changes_revision_not_lineage(tmp_path, monkeypatch):
    _init_db(tmp_path, monkeypatch)
    base = build_test_snapshot(env={"X": "1"})
    changed = build_test_snapshot(env={"X": "2"})
    promote_candidate_snapshot(base)
    promote_candidate_snapshot(changed)

    from alma_bridge.compatibility.profile_store import _connect, ensure_profile_tables

    with _connect() as conn:
        ensure_profile_tables(conn)
        revisions = conn.execute(
            """
            SELECT profile_revision, bridge_manifest_hash FROM compatibility_profiles
            WHERE lineage_key = ? ORDER BY profile_revision
            """,
            (base.profile_lineage_key,),
        ).fetchall()
    assert len(revisions) == 2
    assert revisions[0]["bridge_manifest_hash"] != revisions[1]["bridge_manifest_hash"]
    assert int(revisions[0]["profile_revision"]) == 1
    assert int(revisions[1]["profile_revision"]) == 2
