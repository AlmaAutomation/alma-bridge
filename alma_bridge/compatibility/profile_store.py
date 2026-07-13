from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from alma_bridge.compatibility.profile_models import ProfileCandidateSnapshot
from alma_bridge.config import settings


def _connect() -> sqlite3.Connection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_profile_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS compatibility_profile_candidates (
            candidate_id TEXT PRIMARY KEY,
            source_session_id TEXT NOT NULL,
            source_attempt_number INTEGER NOT NULL,
            candidate_schema_version TEXT NOT NULL,
            program_identity_key TEXT NOT NULL,
            host_compatibility_class_id TEXT NOT NULL,
            bridge_family_key TEXT NOT NULL,
            bridge_manifest_hash TEXT NOT NULL,
            verification_binding_key TEXT NOT NULL,
            profile_lineage_key TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            snapshot_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            promoted_profile_id TEXT,
            promotion_outcome TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_profile_candidates_session
            ON compatibility_profile_candidates(source_session_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_profile_candidates_session_attempt
            ON compatibility_profile_candidates(source_session_id, source_attempt_number);

        CREATE TABLE IF NOT EXISTS compatibility_profile_lineages (
            lineage_key TEXT PRIMARY KEY,
            current_revision INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS compatibility_profiles (
            profile_id TEXT PRIMARY KEY,
            lineage_key TEXT NOT NULL,
            profile_revision INTEGER NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE,
            row_version INTEGER NOT NULL DEFAULT 1,
            lifecycle_state TEXT NOT NULL,
            trust_state TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            executable_hash TEXT NOT NULL,
            program_kind TEXT NOT NULL,
            architecture TEXT NOT NULL,
            product_version TEXT,
            host_compatibility_class_id TEXT NOT NULL,
            bridge_family_key TEXT NOT NULL,
            bridge_manifest_hash TEXT NOT NULL,
            verification_binding_key TEXT NOT NULL,
            strategy_id TEXT NOT NULL,
            policy_id TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            aggregate_confidence REAL NOT NULL DEFAULT 0.0,
            reuse_success_count INTEGER NOT NULL DEFAULT 0,
            reuse_failure_count INTEGER NOT NULL DEFAULT 0,
            source_session_id TEXT NOT NULL,
            source_attempt_number INTEGER NOT NULL,
            candidate_id TEXT NOT NULL,
            verified_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(lineage_key, profile_revision),
            UNIQUE(lineage_key, bridge_manifest_hash, verification_binding_key)
        );
        CREATE INDEX IF NOT EXISTS idx_profiles_lookup
            ON compatibility_profiles(lifecycle_state, executable_hash, host_compatibility_class_id);
        CREATE INDEX IF NOT EXISTS idx_profiles_lineage
            ON compatibility_profiles(lineage_key);

        CREATE TABLE IF NOT EXISTS compatibility_profile_program_fingerprints (
            profile_id TEXT PRIMARY KEY,
            executable_hash TEXT NOT NULL,
            executable_format TEXT NOT NULL,
            architecture TEXT NOT NULL,
            program_kind TEXT NOT NULL,
            product_name TEXT,
            product_version TEXT,
            file_size INTEGER,
            bundled_hashes_json TEXT NOT NULL,
            fingerprint_schema_version TEXT NOT NULL,
            program_identity_key TEXT NOT NULL,
            identity_json TEXT NOT NULL,
            FOREIGN KEY(profile_id) REFERENCES compatibility_profiles(profile_id)
        );

        CREATE TABLE IF NOT EXISTS compatibility_profile_path_aliases (
            alias_id TEXT PRIMARY KEY,
            profile_id TEXT,
            candidate_id TEXT,
            alias_kind TEXT NOT NULL,
            path_raw TEXT,
            path_normalized TEXT,
            username TEXT,
            session_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS compatibility_profile_host_fingerprints (
            profile_id TEXT PRIMARY KEY,
            host_compatibility_class_id TEXT NOT NULL,
            os_family TEXT NOT NULL,
            host_arch TEXT NOT NULL,
            wine_major TEXT,
            proton_family TEXT,
            capability_set_json TEXT NOT NULL,
            gpu_class TEXT,
            kernel_minimum TEXT,
            dependency_versions_json TEXT NOT NULL,
            host_class_json TEXT NOT NULL,
            FOREIGN KEY(profile_id) REFERENCES compatibility_profiles(profile_id)
        );

        CREATE TABLE IF NOT EXISTS compatibility_profile_bridge_config (
            profile_id TEXT PRIMARY KEY,
            bridge_manifest_hash TEXT NOT NULL,
            bridge_family_key TEXT NOT NULL,
            strategy_id TEXT NOT NULL,
            strategy_version TEXT NOT NULL,
            prefix_architecture TEXT,
            windows_version TEXT,
            remediation_protocol_json TEXT NOT NULL,
            winetricks_json TEXT NOT NULL,
            dll_overrides_json TEXT NOT NULL,
            env_json TEXT NOT NULL,
            wrapper_versions_json TEXT NOT NULL,
            config_hashes_json TEXT NOT NULL,
            manifest_json TEXT NOT NULL,
            prefix_reference TEXT,
            FOREIGN KEY(profile_id) REFERENCES compatibility_profiles(profile_id)
        );

        CREATE TABLE IF NOT EXISTS compatibility_profile_verification (
            profile_id TEXT PRIMARY KEY,
            verification_binding_key TEXT NOT NULL,
            policy_id TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            required_checks_json TEXT NOT NULL,
            verifier_ids_json TEXT NOT NULL,
            verifier_versions_json TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            confidence REAL NOT NULL,
            source_session_id TEXT NOT NULL,
            source_attempt_number INTEGER NOT NULL,
            FOREIGN KEY(profile_id) REFERENCES compatibility_profiles(profile_id)
        );

        CREATE TABLE IF NOT EXISTS compatibility_profile_artifacts (
            artifact_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            name TEXT NOT NULL,
            version TEXT,
            source TEXT NOT NULL,
            acquisition_method TEXT NOT NULL,
            checksum_sha256 TEXT NOT NULL,
            signature_status TEXT NOT NULL,
            path_template TEXT,
            FOREIGN KEY(profile_id) REFERENCES compatibility_profiles(profile_id)
        );

        CREATE TABLE IF NOT EXISTS compatibility_profile_verification_attachments (
            attachment_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            attempt_number INTEGER NOT NULL,
            attachment_reason TEXT NOT NULL,
            attachment_idempotency_key TEXT NOT NULL UNIQUE,
            verification_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(profile_id, session_id, attempt_number, attachment_reason),
            FOREIGN KEY(profile_id) REFERENCES compatibility_profiles(profile_id)
        );

        CREATE TABLE IF NOT EXISTS compatibility_profile_invalidations (
            invalidation_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            scope TEXT NOT NULL,
            scope_key TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            FOREIGN KEY(profile_id) REFERENCES compatibility_profiles(profile_id)
        );
        CREATE INDEX IF NOT EXISTS idx_profile_invalidations_lookup
            ON compatibility_profile_invalidations(profile_id, scope, active);

        CREATE TABLE IF NOT EXISTS compatibility_profile_creation_events (
            event_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            candidate_id TEXT,
            profile_id TEXT,
            outcome TEXT NOT NULL,
            error TEXT,
            idempotency_key TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(idempotency_key, outcome)
        );

        CREATE TABLE IF NOT EXISTS compatibility_profile_candidate_events (
            event_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            attempt_number INTEGER NOT NULL,
            candidate_id TEXT,
            outcome TEXT NOT NULL,
            error TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


def init_profile_store() -> None:
    with _connect() as conn:
        ensure_profile_tables(conn)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def persist_candidate_snapshot(snapshot: ProfileCandidateSnapshot) -> str:
    with _connect() as conn:
        ensure_profile_tables(conn)
        conn.execute(
            """
            INSERT OR REPLACE INTO compatibility_profile_candidates (
                candidate_id, source_session_id, source_attempt_number,
                candidate_schema_version, program_identity_key,
                host_compatibility_class_id, bridge_family_key,
                bridge_manifest_hash, verification_binding_key,
                profile_lineage_key, idempotency_key, snapshot_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.candidate_id,
                snapshot.source_session_id,
                snapshot.source_attempt_number,
                snapshot.candidate_schema_version,
                snapshot.program_identity_key,
                snapshot.host_compatibility_class_id,
                snapshot.bridge_family_key,
                snapshot.bridge_manifest_hash,
                snapshot.verification_binding_key,
                snapshot.profile_lineage_key,
                snapshot.idempotency_key,
                json.dumps(snapshot.to_dict()),
                snapshot.created_at,
            ),
        )
        conn.commit()
    return snapshot.candidate_id


def load_candidate_snapshot(candidate_id: str) -> Optional[ProfileCandidateSnapshot]:
    with _connect() as conn:
        ensure_profile_tables(conn)
        row = conn.execute(
            "SELECT snapshot_json FROM compatibility_profile_candidates WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
    if not row:
        return None
    data = json.loads(row["snapshot_json"])
    return ProfileCandidateSnapshot.from_dict(data)


def load_candidate_for_session_attempt(
    session_id: str,
    attempt_number: int,
) -> Optional[ProfileCandidateSnapshot]:
    with _connect() as conn:
        ensure_profile_tables(conn)
        row = conn.execute(
            """
            SELECT snapshot_json FROM compatibility_profile_candidates
            WHERE source_session_id = ? AND source_attempt_number = ?
            """,
            (session_id, attempt_number),
        ).fetchone()
    if not row:
        return None
    return ProfileCandidateSnapshot.from_dict(json.loads(row["snapshot_json"]))


def record_candidate_event(
    *,
    session_id: str,
    attempt_number: int,
    outcome: str,
    candidate_id: Optional[str] = None,
    error: Optional[str] = None,
) -> str:
    event_id = str(uuid4())
    with _connect() as conn:
        ensure_profile_tables(conn)
        conn.execute(
            """
            INSERT INTO compatibility_profile_candidate_events (
                event_id, session_id, attempt_number, candidate_id, outcome, error, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, session_id, attempt_number, candidate_id, outcome, error, _now()),
        )
        conn.commit()
    return event_id


def record_creation_event(
    *,
    session_id: str,
    outcome: str,
    candidate_id: Optional[str] = None,
    profile_id: Optional[str] = None,
    error: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> str:
    event_id = str(uuid4())
    with _connect() as conn:
        ensure_profile_tables(conn)
        conn.execute(
            """
            INSERT INTO compatibility_profile_creation_events (
                event_id, session_id, candidate_id, profile_id, outcome, error,
                idempotency_key, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                session_id,
                candidate_id,
                profile_id,
                outcome,
                error,
                idempotency_key,
                _now(),
            ),
        )
        conn.commit()
    return event_id


def mark_candidate_promoted(candidate_id: str, profile_id: str, outcome: str) -> None:
    with _connect() as conn:
        ensure_profile_tables(conn)
        conn.execute(
            """
            UPDATE compatibility_profile_candidates
            SET promoted_profile_id = ?, promotion_outcome = ?
            WHERE candidate_id = ?
            """,
            (profile_id, outcome, candidate_id),
        )
        conn.commit()


def get_profile_by_idempotency_key(idempotency_key: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        ensure_profile_tables(conn)
        row = conn.execute(
            "SELECT * FROM compatibility_profiles WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
    return dict(row) if row else None


def insert_invalidation(
    *,
    profile_id: str,
    scope: str,
    scope_key: str,
    rule_id: str,
    reason: str,
    evidence: Optional[Dict[str, Any]] = None,
) -> str:
    invalidation_id = str(uuid4())
    with _connect() as conn:
        ensure_profile_tables(conn)
        conn.execute(
            """
            INSERT INTO compatibility_profile_invalidations (
                invalidation_id, profile_id, scope, scope_key, rule_id, reason,
                evidence_json, active, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                invalidation_id,
                profile_id,
                scope,
                scope_key,
                rule_id,
                reason,
                json.dumps(evidence or {}),
                _now(),
            ),
        )
        conn.commit()
    return invalidation_id


def load_profile_bundle(profile_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        ensure_profile_tables(conn)
        profile = conn.execute(
            "SELECT * FROM compatibility_profiles WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()
        if not profile:
            return None
        program = conn.execute(
            "SELECT * FROM compatibility_profile_program_fingerprints WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()
        host = conn.execute(
            "SELECT * FROM compatibility_profile_host_fingerprints WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()
        bridge = conn.execute(
            "SELECT * FROM compatibility_profile_bridge_config WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()
        verification = conn.execute(
            "SELECT * FROM compatibility_profile_verification WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()
        artifacts = conn.execute(
            "SELECT * FROM compatibility_profile_artifacts WHERE profile_id = ?",
            (profile_id,),
        ).fetchall()
        invalidations = conn.execute(
            """
            SELECT * FROM compatibility_profile_invalidations
            WHERE profile_id = ? AND active = 1
            """,
            (profile_id,),
        ).fetchall()
    return {
        "profile": dict(profile),
        "program": dict(program) if program else {},
        "host": dict(host) if host else {},
        "bridge": dict(bridge) if bridge else {},
        "verification": dict(verification) if verification else {},
        "artifacts": [dict(a) for a in artifacts],
        "invalidations": [dict(i) for i in invalidations],
    }


def list_profile_bundles_for_executable(
    executable_hash: str,
    *,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    with _connect() as conn:
        ensure_profile_tables(conn)
        rows = conn.execute(
            """
            SELECT profile_id FROM compatibility_profiles
            WHERE executable_hash = ?
            ORDER BY verified_at DESC LIMIT ?
            """,
            (executable_hash, limit),
        ).fetchall()
    bundles: List[Dict[str, Any]] = []
    for row in rows:
        bundle = load_profile_bundle(str(row["profile_id"]))
        if bundle:
            bundles.append(bundle)
    return bundles
