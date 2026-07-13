from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

from alma_bridge.compatibility.profile_models import ProfileCandidateSnapshot
from alma_bridge.compatibility.profile_store import (
    _connect,
    ensure_profile_tables,
    get_profile_by_idempotency_key,
    mark_candidate_promoted,
)
from alma_bridge.compatibility.profile_fingerprints import FINGERPRINT_SCHEMA_VERSION


def _attachment_idempotency_key(
    profile_id: str,
    session_id: str,
    attempt_number: int,
    attachment_reason: str = "verification_evidence",
) -> str:
    return f"{profile_id}:{session_id}:{attempt_number}:{attachment_reason}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def promote_candidate_snapshot(
    snapshot: ProfileCandidateSnapshot,
) -> Tuple[str, str]:
    """
    Promote immutable candidate into profile row.
    Returns (profile_id, outcome) where outcome is 'created' or 'attached'.
    Transaction: BEGIN IMMEDIATE through commit.
    """
    with _connect() as conn:
        ensure_profile_tables(conn)
        conn.execute("BEGIN IMMEDIATE")

        existing = conn.execute(
            "SELECT profile_id, profile_revision FROM compatibility_profiles WHERE idempotency_key = ?",
            (snapshot.idempotency_key,),
        ).fetchone()

        if existing:
            profile_id = str(existing["profile_id"])
            attachment_key = _attachment_idempotency_key(
                profile_id,
                snapshot.source_session_id,
                snapshot.source_attempt_number,
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO compatibility_profile_verification_attachments (
                    attachment_id, profile_id, session_id, attempt_number,
                    attachment_reason, attachment_idempotency_key,
                    verification_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    profile_id,
                    snapshot.source_session_id,
                    snapshot.source_attempt_number,
                    "verification_evidence",
                    attachment_key,
                    json.dumps(snapshot.verification_payload),
                    _now(),
                ),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO compatibility_profile_creation_events (
                    event_id, session_id, candidate_id, profile_id, outcome, error,
                    idempotency_key, created_at
                ) VALUES (?, ?, ?, ?, 'attached', NULL, ?, ?)
                """,
                (
                    str(uuid4()),
                    snapshot.source_session_id,
                    snapshot.candidate_id,
                    profile_id,
                    snapshot.idempotency_key,
                    _now(),
                ),
            )
            conn.commit()
            mark_candidate_promoted(snapshot.candidate_id, profile_id, "attached")
            return profile_id, "attached"

        now = _now()
        conn.execute(
            """
            INSERT OR IGNORE INTO compatibility_profile_lineages (
                lineage_key, current_revision, created_at, updated_at
            ) VALUES (?, 0, ?, ?)
            """,
            (snapshot.profile_lineage_key, now, now),
        )
        conn.execute(
            """
            UPDATE compatibility_profile_lineages
            SET current_revision = current_revision + 1, updated_at = ?
            WHERE lineage_key = ?
            """,
            (now, snapshot.profile_lineage_key),
        )
        revision_row = conn.execute(
            "SELECT current_revision FROM compatibility_profile_lineages WHERE lineage_key = ?",
            (snapshot.profile_lineage_key,),
        ).fetchone()
        if not revision_row:
            conn.rollback()
            raise RuntimeError("failed to allocate profile revision")
        profile_revision = int(revision_row["current_revision"])

        profile_id = str(uuid4())
        verification = snapshot.verification_payload
        checks = verification.get("checks") or []
        verifier_ids = [str(c.get("verifier_id")) for c in checks if c.get("verifier_id")]
        verifier_versions = [
            str(c.get("verifier_version")) for c in checks if c.get("verifier_version")
        ]
        confidence = float(verification.get("confidence") or 0.0)
        policy = snapshot.verification_binding_payload

        try:
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
                ) VALUES (?, ?, ?, ?, 1, 'VERIFIED', 'locally_verified', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile_id,
                    snapshot.profile_lineage_key,
                    profile_revision,
                    snapshot.idempotency_key,
                    FINGERPRINT_SCHEMA_VERSION,
                    snapshot.program_identity_payload["executable_hash"],
                    snapshot.program_identity_payload["program_kind"],
                    snapshot.program_identity_payload["architecture"],
                    snapshot.program_identity_payload.get("product_version"),
                    snapshot.host_compatibility_class_id,
                    snapshot.bridge_family_key,
                    snapshot.bridge_manifest_hash,
                    snapshot.verification_binding_key,
                    snapshot.strategy_id,
                    policy["policy_id"],
                    policy["policy_version"],
                    confidence,
                    snapshot.source_session_id,
                    snapshot.source_attempt_number,
                    snapshot.candidate_id,
                    now,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError:
            conn.rollback()
            raced = get_profile_by_idempotency_key(snapshot.idempotency_key)
            if raced:
                return promote_candidate_snapshot(snapshot)
            raise

        identity = snapshot.program_identity_payload
        host = snapshot.host_compatibility_class_payload
        manifest = snapshot.bridge_manifest

        conn.execute(
            """
            INSERT INTO compatibility_profile_program_fingerprints (
                profile_id, executable_hash, executable_format, architecture, program_kind,
                product_name, product_version, file_size, bundled_hashes_json,
                fingerprint_schema_version, program_identity_key, identity_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile_id,
                identity["executable_hash"],
                identity["executable_format"],
                identity["architecture"],
                identity["program_kind"],
                None,
                identity.get("product_version"),
                None,
                json.dumps(identity.get("bundled_hashes") or {}),
                identity["fingerprint_schema_version"],
                snapshot.program_identity_key,
                json.dumps(identity),
            ),
        )
        conn.execute(
            """
            INSERT INTO compatibility_profile_host_fingerprints (
                profile_id, host_compatibility_class_id, os_family, host_arch, wine_major,
                proton_family, capability_set_json, gpu_class, kernel_minimum,
                dependency_versions_json, host_class_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile_id,
                snapshot.host_compatibility_class_id,
                host["os_family"],
                host["host_arch"],
                host.get("wine_major"),
                host.get("proton_family"),
                json.dumps(host.get("capability_set") or []),
                host.get("gpu_class"),
                None,
                json.dumps({}),
                json.dumps(host),
            ),
        )
        conn.execute(
            """
            INSERT INTO compatibility_profile_bridge_config (
                profile_id, bridge_manifest_hash, bridge_family_key, strategy_id,
                strategy_version, prefix_architecture, windows_version,
                remediation_protocol_json, winetricks_json, dll_overrides_json, env_json,
                wrapper_versions_json, config_hashes_json, manifest_json, prefix_reference
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile_id,
                snapshot.bridge_manifest_hash,
                snapshot.bridge_family_key,
                snapshot.strategy_id,
                snapshot.strategy_version,
                manifest.get("prefix_architecture"),
                manifest.get("windows_version"),
                json.dumps(manifest.get("remediation_protocol") or []),
                json.dumps(manifest.get("installed_components") or []),
                json.dumps(manifest.get("dll_overrides") or {}),
                json.dumps(manifest.get("environment") or {}),
                json.dumps(manifest.get("wrapper_versions") or {}),
                json.dumps(manifest.get("config_file_hashes") or {}),
                json.dumps(manifest),
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO compatibility_profile_verification (
                profile_id, verification_binding_key, policy_id, policy_version,
                required_checks_json, verifier_ids_json, verifier_versions_json,
                evidence_json, confidence, source_session_id, source_attempt_number
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile_id,
                snapshot.verification_binding_key,
                policy["policy_id"],
                policy["policy_version"],
                json.dumps(policy.get("required_checks") or []),
                json.dumps(verifier_ids),
                json.dumps(verifier_versions),
                json.dumps(verification.get("evidence") or []),
                confidence,
                snapshot.source_session_id,
                snapshot.source_attempt_number,
            ),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO compatibility_profile_verification_attachments (
                attachment_id, profile_id, session_id, attempt_number,
                attachment_reason, attachment_idempotency_key,
                verification_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                profile_id,
                snapshot.source_session_id,
                snapshot.source_attempt_number,
                "verification_evidence",
                _attachment_idempotency_key(
                    profile_id,
                    snapshot.source_session_id,
                    snapshot.source_attempt_number,
                ),
                json.dumps(snapshot.verification_payload),
                now,
            ),
        )
        for artifact in snapshot.artifact_provenance:
            conn.execute(
                """
                INSERT INTO compatibility_profile_artifacts (
                    artifact_id, profile_id, artifact_type, name, version, source,
                    acquisition_method, checksum_sha256, signature_status, path_template
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    profile_id,
                    str(artifact.get("artifact_type") or "unknown"),
                    str(artifact.get("name") or "artifact"),
                    artifact.get("version"),
                    str(artifact.get("source") or "unknown"),
                    str(artifact.get("acquisition_method") or "unknown"),
                    str(artifact.get("checksum_sha256") or ""),
                    str(artifact.get("signature_status") or "hash_verified"),
                    artifact.get("path_template"),
                ),
            )

        conn.execute(
            """
            INSERT OR IGNORE INTO compatibility_profile_creation_events (
                event_id, session_id, candidate_id, profile_id, outcome, error,
                idempotency_key, created_at
            ) VALUES (?, ?, ?, ?, 'created', NULL, ?, ?)
            """,
            (
                str(uuid4()),
                snapshot.source_session_id,
                snapshot.candidate_id,
                profile_id,
                snapshot.idempotency_key,
                now,
            ),
        )
        conn.commit()
        mark_candidate_promoted(snapshot.candidate_id, profile_id, "created")
        return profile_id, "created"
