from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional
from uuid import uuid4

from alma_bridge.compatibility.profile_shadow_validation_models import (
    FAILURE_ANALYSIS_SCHEMA_VERSION,
    LABEL_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    ShadowLabelInput,
)
from alma_bridge.compatibility.profile_store import _connect, ensure_profile_tables
from alma_bridge.compatibility.profile_shadow_store import ensure_shadow_tables
from alma_bridge.config import settings

_MANIFEST_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "validation" / "shadow_scenario_manifest_v1.json"
)


def ensure_validation_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS compatibility_profile_shadow_scenarios (
            scenario_id TEXT PRIMARY KEY,
            scenario_category TEXT NOT NULL,
            manifest_version TEXT NOT NULL,
            manifest_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_shadow_scenarios_category
            ON compatibility_profile_shadow_scenarios(scenario_category);

        CREATE TABLE IF NOT EXISTS compatibility_profile_shadow_validation_runs (
            validation_run_id TEXT PRIMARY KEY,
            shadow_event_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            scenario_id TEXT NOT NULL,
            scenario_category TEXT NOT NULL,
            manifest_version TEXT NOT NULL,
            program_kind TEXT,
            application_family TEXT,
            registered_at TEXT NOT NULL,
            UNIQUE(session_id, scenario_id),
            FOREIGN KEY(scenario_id) REFERENCES compatibility_profile_shadow_scenarios(scenario_id)
        );
        CREATE INDEX IF NOT EXISTS idx_shadow_validation_runs_event
            ON compatibility_profile_shadow_validation_runs(shadow_event_id);
        CREATE INDEX IF NOT EXISTS idx_shadow_validation_runs_category
            ON compatibility_profile_shadow_validation_runs(scenario_category);

        CREATE TABLE IF NOT EXISTS compatibility_profile_shadow_labels (
            label_id TEXT PRIMARY KEY,
            shadow_event_id TEXT NOT NULL,
            profile_id TEXT,
            label_type TEXT NOT NULL,
            label_source TEXT NOT NULL,
            reviewer TEXT NOT NULL,
            reason TEXT NOT NULL,
            evidence_refs_json TEXT NOT NULL,
            label_schema_version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(shadow_event_id, profile_id, label_type, label_schema_version)
        );
        CREATE INDEX IF NOT EXISTS idx_shadow_labels_event
            ON compatibility_profile_shadow_labels(shadow_event_id);
        CREATE INDEX IF NOT EXISTS idx_shadow_labels_type
            ON compatibility_profile_shadow_labels(label_type);

        CREATE TABLE IF NOT EXISTS compatibility_profile_shadow_failure_analysis (
            analysis_id TEXT PRIMARY KEY,
            shadow_event_id TEXT NOT NULL,
            profile_id TEXT,
            profile_revision INTEGER,
            scenario_category TEXT,
            failure_kind TEXT NOT NULL,
            eligibility_reasons_json TEXT NOT NULL,
            ranking_components_json TEXT NOT NULL,
            drift_dimensions_json TEXT NOT NULL,
            actual_evidence_json TEXT NOT NULL,
            verification_result_ref TEXT,
            root_cause_classification TEXT,
            proposed_correction TEXT,
            defect_category TEXT NOT NULL,
            analysis_schema_version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(shadow_event_id, profile_id, failure_kind, analysis_schema_version)
        );
        CREATE INDEX IF NOT EXISTS idx_shadow_failure_event
            ON compatibility_profile_shadow_failure_analysis(shadow_event_id);
        CREATE INDEX IF NOT EXISTS idx_shadow_failure_kind
            ON compatibility_profile_shadow_failure_analysis(failure_kind);
        """
    )
    conn.commit()


def init_validation_store() -> None:
    with _connect() as conn:
        ensure_profile_tables(conn)
        ensure_shadow_tables(conn)
        ensure_validation_tables(conn)
    sync_scenario_manifest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_manifest_file() -> Dict[str, Any]:
    if not _MANIFEST_PATH.is_file():
        return {"schema": MANIFEST_SCHEMA_VERSION, "version": "1.0.0", "scenarios": []}
    return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))


def sync_scenario_manifest() -> int:
    manifest = load_manifest_file()
    version = str(manifest.get("version") or "1.0.0")
    scenarios = list(manifest.get("scenarios") or [])
    now = _now()
    with _connect() as conn:
        ensure_validation_tables(conn)
        for scenario in scenarios:
            scenario_id = str(scenario["scenario_id"])
            conn.execute(
                """
                INSERT INTO compatibility_profile_shadow_scenarios (
                    scenario_id, scenario_category, manifest_version, manifest_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(scenario_id) DO UPDATE SET
                    scenario_category = excluded.scenario_category,
                    manifest_version = excluded.manifest_version,
                    manifest_json = excluded.manifest_json,
                    updated_at = excluded.updated_at
                """,
                (
                    scenario_id,
                    str(scenario.get("scenario_category") or scenario_id),
                    version,
                    json.dumps(scenario),
                    now,
                    now,
                ),
            )
        conn.commit()
    return len(scenarios)


def get_scenario(scenario_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        ensure_validation_tables(conn)
        row = conn.execute(
            "SELECT * FROM compatibility_profile_shadow_scenarios WHERE scenario_id = ?",
            (scenario_id,),
        ).fetchone()
    return dict(row) if row else None


def register_validation_run(
    *,
    session_id: str,
    scenario_id: str,
    shadow_event_id: Optional[str] = None,
    program_kind: Optional[str] = None,
    application_family: Optional[str] = None,
) -> str:
    scenario = get_scenario(scenario_id)
    if not scenario:
        raise ValueError(f"unknown scenario_id: {scenario_id}")

    if not shadow_event_id:
        from alma_bridge.compatibility.profile_shadow_store import load_shadow_prediction

        prediction = load_shadow_prediction(session_id)
        if not prediction:
            raise ValueError(f"no shadow prediction for session_id={session_id}")
        shadow_event_id = str(prediction["shadow_event_id"])

    manifest = json.loads(scenario["manifest_json"])
    run_id = str(uuid4())
    with _connect() as conn:
        ensure_validation_tables(conn)
        conn.execute(
            """
            INSERT OR IGNORE INTO compatibility_profile_shadow_validation_runs (
                validation_run_id, shadow_event_id, session_id, scenario_id,
                scenario_category, manifest_version, program_kind, application_family,
                registered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                shadow_event_id,
                session_id,
                scenario_id,
                str(scenario["scenario_category"]),
                str(scenario["manifest_version"]),
                program_kind,
                application_family,
                _now(),
            ),
        )
        conn.commit()
    return run_id


def add_label(label: ShadowLabelInput) -> str:
    from alma_bridge.compatibility.profile_shadow_validation_models import VALID_LABEL_TYPES

    if label.label_type not in VALID_LABEL_TYPES:
        raise ValueError(f"invalid label_type: {label.label_type}")

    label_id = str(uuid4())
    with _connect() as conn:
        ensure_validation_tables(conn)
        conn.execute(
            """
            INSERT OR IGNORE INTO compatibility_profile_shadow_labels (
                label_id, shadow_event_id, profile_id, label_type, label_source,
                reviewer, reason, evidence_refs_json, label_schema_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                label_id,
                label.shadow_event_id,
                label.profile_id,
                label.label_type,
                label.label_source,
                label.reviewer,
                label.reason,
                json.dumps(label.evidence_refs or []),
                LABEL_SCHEMA_VERSION,
                _now(),
            ),
        )
        conn.commit()
    return label_id


def list_labels(shadow_event_id: Optional[str] = None) -> List[Dict[str, Any]]:
    with _connect() as conn:
        ensure_validation_tables(conn)
        if shadow_event_id:
            rows = conn.execute(
                "SELECT * FROM compatibility_profile_shadow_labels WHERE shadow_event_id = ?",
                (shadow_event_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM compatibility_profile_shadow_labels ORDER BY created_at DESC"
            ).fetchall()
    return [dict(row) for row in rows]


def record_failure_analysis(
    *,
    shadow_event_id: str,
    failure_kind: str,
    defect_category: str,
    scenario_category: Optional[str] = None,
    profile_id: Optional[str] = None,
    profile_revision: Optional[int] = None,
    eligibility_reasons: Optional[List[str]] = None,
    ranking_components: Optional[Mapping[str, Any]] = None,
    drift_dimensions: Optional[List[Mapping[str, Any]]] = None,
    actual_evidence: Optional[Mapping[str, Any]] = None,
    verification_result_ref: Optional[str] = None,
    root_cause_classification: Optional[str] = None,
    proposed_correction: Optional[str] = None,
) -> str:
    analysis_id = str(uuid4())
    with _connect() as conn:
        ensure_validation_tables(conn)
        conn.execute(
            """
            INSERT OR IGNORE INTO compatibility_profile_shadow_failure_analysis (
                analysis_id, shadow_event_id, profile_id, profile_revision,
                scenario_category, failure_kind, eligibility_reasons_json,
                ranking_components_json, drift_dimensions_json, actual_evidence_json,
                verification_result_ref, root_cause_classification, proposed_correction,
                defect_category, analysis_schema_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_id,
                shadow_event_id,
                profile_id,
                profile_revision,
                scenario_category,
                failure_kind,
                json.dumps(eligibility_reasons or []),
                json.dumps(dict(ranking_components or {})),
                json.dumps(list(drift_dimensions or [])),
                json.dumps(dict(actual_evidence or {})),
                verification_result_ref,
                root_cause_classification,
                proposed_correction,
                defect_category,
                FAILURE_ANALYSIS_SCHEMA_VERSION,
                _now(),
            ),
        )
        conn.commit()
    return analysis_id


def list_failure_analyses(
    *,
    shadow_event_id: Optional[str] = None,
    failure_kind: Optional[str] = None,
) -> List[Dict[str, Any]]:
    with _connect() as conn:
        ensure_validation_tables(conn)
        query = "SELECT * FROM compatibility_profile_shadow_failure_analysis WHERE 1=1"
        params: List[Any] = []
        if shadow_event_id:
            query += " AND shadow_event_id = ?"
            params.append(shadow_event_id)
        if failure_kind:
            query += " AND failure_kind = ?"
            params.append(failure_kind)
        query += " ORDER BY created_at DESC"
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]
