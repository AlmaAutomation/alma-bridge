from __future__ import annotations

from alma_bridge.compatibility.profile_fingerprints import (
    BRIDGE_FAMILY_SCHEMA,
    build_bridge_family_key,
    build_bridge_family_payload,
    build_bridge_manifest_hash,
    build_idempotency_key,
    build_profile_lineage_key,
    build_program_identity_key,
    build_program_identity_payload,
    build_verification_binding_key,
    build_verification_binding_payload,
)
from alma_bridge.compatibility.profile_host_class import (
    build_host_compatibility_class_id,
    build_host_compatibility_class_payload,
)
from tests.profile_test_helpers import build_test_snapshot, sample_hardware


def test_program_identity_excludes_paths():
    payload_a = build_program_identity_payload(
        executable_hash="deadbeef",
        executable_format="script",
        architecture="x86_64",
        program_kind="native_script",
    )
    payload_b = build_program_identity_payload(
        executable_hash="deadbeef",
        executable_format="script",
        architecture="x86_64",
        program_kind="native_script",
    )
    assert "path" not in payload_a
    assert "normalized_path" not in payload_a
    assert build_program_identity_key(payload_a) == build_program_identity_key(payload_b)


def test_bridge_family_key_canonical_payload():
    payload = build_bridge_family_payload(
        strategy_id="wine_default",
        runtime_family="wine",
        program_kind="pe_windows",
        protocol_family="generic",
        bridge_architecture_class="wine_pe_pe_windows",
    )
    assert payload["schema"] == BRIDGE_FAMILY_SCHEMA
    assert set(payload.keys()) == {
        "schema",
        "strategy_id",
        "runtime_family",
        "program_kind",
        "protocol_family",
        "bridge_architecture_class",
    }
    assert "bridge_manifest_hash" not in payload
    assert "remediation_protocol" not in payload
    key = build_bridge_family_key(payload)
    assert len(key) == 64


def test_lineage_and_idempotency_keys():
    program_key = build_program_identity_key(
        build_program_identity_payload(
            executable_hash="hash1",
            executable_format="script",
            architecture="x86_64",
            program_kind="native_script",
        )
    )
    host_id = build_host_compatibility_class_id(
        build_host_compatibility_class_payload(sample_hardware())
    )
    family_key = build_bridge_family_key(
        build_bridge_family_payload(
            strategy_id="native_direct",
            runtime_family="native",
            program_kind="native_script",
            protocol_family="generic",
            bridge_architecture_class="native_script",
        )
    )
    binding_key = build_verification_binding_key(
        build_verification_binding_payload(
            policy_id="bridge_aggregate_v1",
            policy_version="1.0.0",
            required_checks=["exit_code_zero"],
        )
    )
    lineage = build_profile_lineage_key(
        program_identity_key=program_key,
        host_compatibility_class_id=host_id,
        bridge_family_key=family_key,
        verification_binding_key=binding_key,
    )
    manifest_hash = build_bridge_manifest_hash({"schema": "bridge_manifest_v1", "env": {}})
    idem = build_idempotency_key(
        profile_lineage_key=lineage,
        bridge_manifest_hash=manifest_hash,
        verification_binding_key=binding_key,
    )
    assert lineage != idem
    assert len(lineage) == 64
    assert len(idem) == 64


def test_same_family_changed_manifest_same_lineage_new_revision(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "outcomes.db")
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profiles_enabled", True)
    monkeypatch.setattr(
        "alma_bridge.config.settings.compatibility_profile_creation_enabled", True
    )

    snap_a = build_test_snapshot(env={"FOO": "1"})
    snap_b = build_test_snapshot(env={"FOO": "2"})
    assert snap_a.bridge_family_key == snap_b.bridge_family_key
    assert snap_a.profile_lineage_key == snap_b.profile_lineage_key
    assert snap_a.bridge_manifest_hash != snap_b.bridge_manifest_hash
    assert snap_a.idempotency_key != snap_b.idempotency_key

    from alma_bridge.compatibility.profile_lineage import promote_candidate_snapshot
    from alma_bridge.storage import outcomes

    outcomes.init_outcome_store()
    _, outcome_a = promote_candidate_snapshot(snap_a)
    _, outcome_b = promote_candidate_snapshot(snap_b)
    assert outcome_a == "created"
    assert outcome_b == "created"

    from alma_bridge.compatibility.profile_store import _connect, ensure_profile_tables

    with _connect() as conn:
        ensure_profile_tables(conn)
        rows = conn.execute(
            """
            SELECT profile_revision FROM compatibility_profiles
            WHERE lineage_key = ? ORDER BY profile_revision
            """,
            (snap_a.profile_lineage_key,),
        ).fetchall()
    assert [int(r["profile_revision"]) for r in rows] == [1, 2]


def test_changed_bridge_family_new_lineage(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "outcomes.db")

    snap_a = build_test_snapshot(strategy_id="native_direct", runtime="native")
    snap_b = build_test_snapshot(strategy_id="wine_default", runtime="wine")
    assert snap_a.bridge_family_key != snap_b.bridge_family_key
    assert snap_a.profile_lineage_key != snap_b.profile_lineage_key


def test_wineprefix_path_does_not_change_manifest_identity(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "outcomes.db")

    snap_a = build_test_snapshot(
        strategy_id="wine_default",
        runtime="wine",
        env={"WINEPREFIX": "/tmp/prefix-a"},
    )
    snap_b = build_test_snapshot(
        session_id="sess-b",
        strategy_id="wine_default",
        runtime="wine",
        env={"WINEPREFIX": "/tmp/prefix-b"},
    )
    assert snap_a.bridge_manifest_hash == snap_b.bridge_manifest_hash
    assert snap_a.idempotency_key == snap_b.idempotency_key


def test_same_manifest_attaches_without_new_revision(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "outcomes.db")
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profiles_enabled", True)
    monkeypatch.setattr(
        "alma_bridge.config.settings.compatibility_profile_creation_enabled", True
    )

    from alma_bridge.compatibility.profile_lineage import promote_candidate_snapshot
    from alma_bridge.storage import outcomes

    outcomes.init_outcome_store()
    snap_a = build_test_snapshot(session_id="sess-a")
    snap_b = build_test_snapshot(session_id="sess-b")
    assert snap_a.idempotency_key == snap_b.idempotency_key

    profile_id_a, outcome_a = promote_candidate_snapshot(snap_a)
    profile_id_b, outcome_b = promote_candidate_snapshot(snap_b)
    assert outcome_a == "created"
    assert outcome_b == "attached"
    assert profile_id_a == profile_id_b

    from alma_bridge.compatibility.profile_store import _connect, ensure_profile_tables

    with _connect() as conn:
        ensure_profile_tables(conn)
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM compatibility_profiles WHERE lineage_key = ?",
            (snap_a.profile_lineage_key,),
        ).fetchone()["c"]
        attachments = conn.execute(
            "SELECT COUNT(*) AS c FROM compatibility_profile_verification_attachments WHERE profile_id = ?",
            (profile_id_a,),
        ).fetchone()["c"]
    assert count == 1
    assert attachments == 2
