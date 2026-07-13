from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional
from uuid import uuid4

from alma_bridge.compatibility.profile_shadow_models import (
    ACTUAL_OUTCOME_SCHEMA_VERSION,
    COMPARISON_SCHEMA_VERSION,
    PREDICTION_SCHEMA_VERSION,
    SHADOW_EVALUATION_VERSION,
    ShadowCandidateEvaluation,
)
from alma_bridge.compatibility.profile_store import _connect, ensure_profile_tables


def ensure_shadow_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS compatibility_profile_shadow_predictions (
            shadow_event_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            correlation_id TEXT NOT NULL,
            prediction_schema_version TEXT NOT NULL,
            shadow_evaluation_version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            program_identity_key TEXT NOT NULL,
            executable_hash TEXT NOT NULL,
            host_compatibility_class_id TEXT NOT NULL,
            ranking_formula_id TEXT,
            ranking_formula_version TEXT,
            ranking_status TEXT NOT NULL,
            selected_profile_id TEXT,
            selected_profile_revision INTEGER,
            predicted_strategy_id TEXT,
            predicted_bridge_family_key TEXT,
            predicted_remediation_protocol_json TEXT,
            feature_flags_json TEXT NOT NULL,
            model_version TEXT,
            candidate_count INTEGER NOT NULL DEFAULT 0,
            eligible_count INTEGER NOT NULL DEFAULT 0,
            rejected_count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(session_id, shadow_evaluation_version)
        );
        CREATE INDEX IF NOT EXISTS idx_shadow_predictions_session
            ON compatibility_profile_shadow_predictions(session_id);
        CREATE INDEX IF NOT EXISTS idx_shadow_predictions_executable
            ON compatibility_profile_shadow_predictions(executable_hash);
        CREATE INDEX IF NOT EXISTS idx_shadow_predictions_host
            ON compatibility_profile_shadow_predictions(host_compatibility_class_id);
        CREATE INDEX IF NOT EXISTS idx_shadow_predictions_winner
            ON compatibility_profile_shadow_predictions(selected_profile_id);
        CREATE INDEX IF NOT EXISTS idx_shadow_predictions_created
            ON compatibility_profile_shadow_predictions(created_at);

        CREATE TABLE IF NOT EXISTS compatibility_profile_shadow_candidates (
            shadow_candidate_id TEXT PRIMARY KEY,
            shadow_event_id TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            profile_revision INTEGER NOT NULL,
            lifecycle_state TEXT NOT NULL,
            trust_state TEXT NOT NULL,
            eligibility_status TEXT NOT NULL,
            trust_category TEXT NOT NULL,
            rejection_reason_codes_json TEXT NOT NULL,
            scoped_invalidations_json TEXT NOT NULL,
            host_match_dimensions_json TEXT NOT NULL,
            bridge_family_match_dimensions_json TEXT NOT NULL,
            verification_binding_compatible INTEGER NOT NULL,
            drift_prediction_result TEXT NOT NULL,
            drift_dimensions_json TEXT NOT NULL,
            ranking_status TEXT NOT NULL,
            ranking_components_json TEXT NOT NULL,
            ml_model_version TEXT,
            ml_feature_vector_json TEXT,
            ml_raw_score REAL,
            final_rank_score REAL,
            winner_selectable INTEGER NOT NULL,
            FOREIGN KEY(shadow_event_id) REFERENCES compatibility_profile_shadow_predictions(shadow_event_id)
        );
        CREATE INDEX IF NOT EXISTS idx_shadow_candidates_event
            ON compatibility_profile_shadow_candidates(shadow_event_id);
        CREATE INDEX IF NOT EXISTS idx_shadow_candidates_profile
            ON compatibility_profile_shadow_candidates(profile_id);
        CREATE INDEX IF NOT EXISTS idx_shadow_candidates_eligibility
            ON compatibility_profile_shadow_candidates(eligibility_status);
        CREATE INDEX IF NOT EXISTS idx_shadow_candidates_trust
            ON compatibility_profile_shadow_candidates(trust_category);

        CREATE TABLE IF NOT EXISTS compatibility_profile_shadow_actual_outcomes (
            actual_outcome_id TEXT PRIMARY KEY,
            shadow_event_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            actual_outcome_schema_version TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            terminal_session_state TEXT NOT NULL,
            actual_success INTEGER NOT NULL,
            actual_strategy_id TEXT,
            actual_bridge_family_key TEXT,
            actual_bridge_manifest_hash TEXT,
            actual_remediation_protocol_json TEXT,
            winning_attempt_number INTEGER,
            verification_result_ref TEXT,
            verification_policy_id TEXT,
            verification_policy_version TEXT,
            failure_signature TEXT,
            fallback_indicators_json TEXT,
            escalation_indicators_json TEXT,
            profile_candidate_id TEXT,
            UNIQUE(session_id, shadow_event_id)
        );
        CREATE INDEX IF NOT EXISTS idx_shadow_actual_session
            ON compatibility_profile_shadow_actual_outcomes(session_id);
        CREATE INDEX IF NOT EXISTS idx_shadow_actual_success
            ON compatibility_profile_shadow_actual_outcomes(actual_success);

        CREATE TABLE IF NOT EXISTS compatibility_profile_shadow_comparisons (
            comparison_id TEXT PRIMARY KEY,
            shadow_event_id TEXT NOT NULL,
            actual_outcome_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            comparison_schema_version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            predicted_profile_selected INTEGER NOT NULL,
            predicted_strategy_agreement INTEGER,
            predicted_bridge_family_agreement INTEGER,
            predicted_remediation_overlap REAL,
            predicted_manifest_agreement INTEGER,
            predicted_eligibility_precision INTEGER,
            false_eligibility INTEGER,
            false_rejection INTEGER,
            rank_agreement INTEGER,
            drift_prediction_correct INTEGER,
            actual_verification_success INTEGER,
            duplicate_predicted_lineage INTEGER,
            reconstruction_required INTEGER,
            indeterminate INTEGER NOT NULL DEFAULT 0,
            indeterminate_reason TEXT,
            metrics_json TEXT NOT NULL,
            UNIQUE(shadow_event_id, actual_outcome_id)
        );
        CREATE INDEX IF NOT EXISTS idx_shadow_comparisons_session
            ON compatibility_profile_shadow_comparisons(session_id);

        CREATE TABLE IF NOT EXISTS compatibility_profile_shadow_events (
            event_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            shadow_event_id TEXT,
            event_type TEXT NOT NULL,
            error TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


def init_shadow_store() -> None:
    with _connect() as conn:
        ensure_profile_tables(conn)
        ensure_shadow_tables(conn)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_shadow_prediction(session_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        ensure_profile_tables(conn)
        ensure_shadow_tables(conn)
        row = conn.execute(
            """
            SELECT * FROM compatibility_profile_shadow_predictions
            WHERE session_id = ? AND shadow_evaluation_version = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (session_id, SHADOW_EVALUATION_VERSION),
        ).fetchone()
    return dict(row) if row else None


def load_shadow_candidates(shadow_event_id: str) -> List[Dict[str, Any]]:
    with _connect() as conn:
        ensure_profile_tables(conn)
        ensure_shadow_tables(conn)
        rows = conn.execute(
            "SELECT * FROM compatibility_profile_shadow_candidates WHERE shadow_event_id = ?",
            (shadow_event_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def persist_shadow_prediction(
    *,
    shadow_event_id: str,
    session_id: str,
    correlation_id: str,
    program_identity_key: str,
    executable_hash: str,
    host_compatibility_class_id: str,
    ranking_formula_id: str,
    ranking_formula_version: str,
    ranking_status: str,
    selected_profile_id: Optional[str],
    selected_profile_revision: Optional[int],
    predicted_strategy_id: Optional[str],
    predicted_bridge_family_key: Optional[str],
    predicted_remediation_protocol: List[Dict[str, str]],
    feature_flags: Mapping[str, bool],
    model_version: Optional[str],
    candidates: List[ShadowCandidateEvaluation],
) -> str:
    eligible = sum(1 for c in candidates if c.eligibility_status == "eligible")
    rejected = sum(1 for c in candidates if c.eligibility_status == "rejected")
    with _connect() as conn:
        ensure_profile_tables(conn)
        ensure_shadow_tables(conn)
        conn.execute(
            """
            INSERT OR IGNORE INTO compatibility_profile_shadow_predictions (
                shadow_event_id, session_id, correlation_id, prediction_schema_version,
                shadow_evaluation_version, created_at, program_identity_key, executable_hash,
                host_compatibility_class_id, ranking_formula_id, ranking_formula_version,
                ranking_status, selected_profile_id, selected_profile_revision,
                predicted_strategy_id, predicted_bridge_family_key,
                predicted_remediation_protocol_json, feature_flags_json, model_version,
                candidate_count, eligible_count, rejected_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                shadow_event_id,
                session_id,
                correlation_id,
                PREDICTION_SCHEMA_VERSION,
                SHADOW_EVALUATION_VERSION,
                _now(),
                program_identity_key,
                executable_hash,
                host_compatibility_class_id,
                ranking_formula_id,
                ranking_formula_version,
                ranking_status,
                selected_profile_id,
                selected_profile_revision,
                predicted_strategy_id,
                predicted_bridge_family_key,
                json.dumps(predicted_remediation_protocol),
                json.dumps(dict(feature_flags)),
                model_version,
                len(candidates),
                eligible,
                rejected,
            ),
        )
        for candidate in candidates:
            conn.execute(
                """
                INSERT INTO compatibility_profile_shadow_candidates (
                    shadow_candidate_id, shadow_event_id, profile_id, profile_revision,
                    lifecycle_state, trust_state, eligibility_status, trust_category,
                    rejection_reason_codes_json, scoped_invalidations_json,
                    host_match_dimensions_json, bridge_family_match_dimensions_json,
                    verification_binding_compatible, drift_prediction_result,
                    drift_dimensions_json, ranking_status, ranking_components_json,
                    ml_model_version, ml_feature_vector_json, ml_raw_score,
                    final_rank_score, winner_selectable
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    shadow_event_id,
                    candidate.profile_id,
                    candidate.profile_revision,
                    candidate.lifecycle_state,
                    candidate.trust_state,
                    candidate.eligibility_status,
                    candidate.trust_category,
                    json.dumps(candidate.rejection_reason_codes),
                    json.dumps(candidate.scoped_invalidations_applied),
                    json.dumps(candidate.host_match_dimensions),
                    json.dumps(candidate.bridge_family_match_dimensions),
                    1 if candidate.verification_binding_compatible else 0,
                    candidate.drift_prediction_result,
                    json.dumps(
                        [
                            {
                                "dimension": d.dimension,
                                "status": d.status,
                                "reason_code": d.reason_code,
                                "expected": d.expected,
                                "observed": d.observed,
                                "severity": d.severity,
                            }
                            for d in candidate.drift_dimensions
                        ]
                    ),
                    candidate.ranking_status,
                    json.dumps(candidate.ranking_components),
                    candidate.ml_model_version,
                    json.dumps(candidate.ml_feature_vector or {}),
                    candidate.ml_raw_score,
                    candidate.final_rank_score,
                    1 if candidate.winner_selectable else 0,
                ),
            )
        conn.commit()
    return shadow_event_id


def persist_shadow_actual_outcome(
    *,
    actual_outcome_id: str,
    shadow_event_id: str,
    session_id: str,
    terminal_session_state: str,
    actual_success: bool,
    actual_strategy_id: Optional[str],
    actual_bridge_family_key: Optional[str],
    actual_bridge_manifest_hash: Optional[str],
    actual_remediation_protocol: Optional[List[Dict[str, str]]],
    winning_attempt_number: Optional[int],
    verification_result_ref: Optional[str],
    verification_policy_id: Optional[str],
    verification_policy_version: Optional[str],
    failure_signature: Optional[str],
    fallback_indicators: Optional[List[str]],
    escalation_indicators: Optional[List[str]],
    profile_candidate_id: Optional[str],
    completed_at: str,
) -> str:
    with _connect() as conn:
        ensure_profile_tables(conn)
        ensure_shadow_tables(conn)
        conn.execute(
            """
            INSERT OR IGNORE INTO compatibility_profile_shadow_actual_outcomes (
                actual_outcome_id, shadow_event_id, session_id, actual_outcome_schema_version,
                completed_at, terminal_session_state, actual_success, actual_strategy_id,
                actual_bridge_family_key, actual_bridge_manifest_hash,
                actual_remediation_protocol_json, winning_attempt_number,
                verification_result_ref, verification_policy_id, verification_policy_version,
                failure_signature, fallback_indicators_json, escalation_indicators_json,
                profile_candidate_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                actual_outcome_id,
                shadow_event_id,
                session_id,
                ACTUAL_OUTCOME_SCHEMA_VERSION,
                completed_at,
                terminal_session_state,
                1 if actual_success else 0,
                actual_strategy_id,
                actual_bridge_family_key,
                actual_bridge_manifest_hash,
                json.dumps(actual_remediation_protocol or []),
                winning_attempt_number,
                verification_result_ref,
                verification_policy_id,
                verification_policy_version,
                failure_signature,
                json.dumps(fallback_indicators or []),
                json.dumps(escalation_indicators or []),
                profile_candidate_id,
            ),
        )
        conn.commit()
    return actual_outcome_id


def persist_shadow_comparison(
    *,
    shadow_event_id: str,
    actual_outcome_id: str,
    session_id: str,
    metrics: Mapping[str, Any],
) -> str:
    comparison_id = str(uuid4())
    with _connect() as conn:
        ensure_profile_tables(conn)
        ensure_shadow_tables(conn)
        conn.execute(
            """
            INSERT OR IGNORE INTO compatibility_profile_shadow_comparisons (
                comparison_id, shadow_event_id, actual_outcome_id, session_id,
                comparison_schema_version, created_at, predicted_profile_selected,
                predicted_strategy_agreement, predicted_bridge_family_agreement,
                predicted_remediation_overlap, predicted_manifest_agreement,
                predicted_eligibility_precision, false_eligibility, false_rejection,
                rank_agreement, drift_prediction_correct, actual_verification_success,
                duplicate_predicted_lineage, reconstruction_required, indeterminate,
                indeterminate_reason, metrics_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                comparison_id,
                shadow_event_id,
                actual_outcome_id,
                session_id,
                COMPARISON_SCHEMA_VERSION,
                _now(),
                int(metrics.get("predicted_profile_selected") or 0),
                metrics.get("predicted_strategy_agreement"),
                metrics.get("predicted_bridge_family_agreement"),
                metrics.get("predicted_remediation_overlap"),
                metrics.get("predicted_manifest_agreement"),
                metrics.get("predicted_eligibility_precision"),
                metrics.get("false_eligibility"),
                metrics.get("false_rejection"),
                metrics.get("rank_agreement"),
                metrics.get("drift_prediction_correct"),
                metrics.get("actual_verification_success"),
                metrics.get("duplicate_predicted_lineage"),
                metrics.get("reconstruction_required"),
                int(metrics.get("indeterminate") or 0),
                metrics.get("indeterminate_reason"),
                json.dumps(dict(metrics)),
            ),
        )
        conn.commit()
    return comparison_id


def record_shadow_event(
    *,
    session_id: str,
    event_type: str,
    shadow_event_id: Optional[str] = None,
    error: Optional[str] = None,
) -> str:
    event_id = str(uuid4())
    with _connect() as conn:
        ensure_profile_tables(conn)
        ensure_shadow_tables(conn)
        conn.execute(
            """
            INSERT INTO compatibility_profile_shadow_events (
                event_id, session_id, shadow_event_id, event_type, error, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, session_id, shadow_event_id, event_type, error, _now()),
        )
        conn.commit()
    return event_id
