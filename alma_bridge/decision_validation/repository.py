"""Append-only SQLite store for decision plan validation reports."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from alma_bridge.config import settings
from alma_bridge.decision_validation.models import (
    DecisionPlanDryRunReport,
    PlanValidationStatus,
    ValidationCheck,
    ValidationCheckCategory,
    ValidationCheckSeverity,
)


def _connect() -> sqlite3.Connection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_decision_validation_store() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS decision_plan_validations (
                validation_id TEXT PRIMARY KEY,
                plan_id TEXT NOT NULL,
                plan_version TEXT NOT NULL,
                plan_digest TEXT NOT NULL,
                review_id TEXT NOT NULL,
                session_id TEXT,
                application_fingerprint TEXT NOT NULL,
                status TEXT NOT NULL,
                has_warnings INTEGER NOT NULL DEFAULT 0,
                approval_stale INTEGER NOT NULL DEFAULT 0,
                checks TEXT NOT NULL DEFAULT '[]',
                validated_at TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'dry_run',
                execution_performed INTEGER NOT NULL DEFAULT 0,
                mutations_performed INTEGER NOT NULL DEFAULT 0,
                disclaimer TEXT NOT NULL,
                evidence_references TEXT NOT NULL DEFAULT '[]',
                schema_version TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_decision_validations_plan
                ON decision_plan_validations(plan_id, validated_at);
            """
        )
        conn.commit()
        _ensure_has_warnings_column(conn)


def _ensure_has_warnings_column(conn: sqlite3.Connection) -> None:
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(decision_plan_validations)").fetchall()
    }
    if "has_warnings" not in columns:
        conn.execute(
            "ALTER TABLE decision_plan_validations ADD COLUMN has_warnings INTEGER NOT NULL DEFAULT 0"
        )
        conn.commit()


def append_validation(report: DecisionPlanDryRunReport) -> DecisionPlanDryRunReport:
    init_decision_validation_store()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO decision_plan_validations (
                validation_id, plan_id, plan_version, plan_digest, review_id,
                session_id, application_fingerprint, status, has_warnings, approval_stale,
                checks, validated_at, mode, execution_performed, mutations_performed,
                disclaimer, evidence_references, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.validation_id,
                report.plan_id,
                report.plan_version,
                report.plan_digest,
                report.review_id,
                report.session_id,
                report.application_fingerprint,
                report.status.value,
                int(report.has_warnings),
                int(report.approval_stale),
                json.dumps([item.model_dump(mode="json") for item in report.checks]),
                report.validated_at,
                report.mode,
                0,
                0,
                report.disclaimer,
                json.dumps(
                    [ref.model_dump(mode="json") for ref in report.evidence_references]
                ),
                report.schema_version,
            ),
        )
        conn.commit()
    return report


def _row_to_report(row: sqlite3.Row) -> DecisionPlanDryRunReport:
    from alma_bridge.knowledge.models import KnowledgeEvidenceReference

    checks_raw = json.loads(row["checks"] or "[]")
    refs_raw = json.loads(row["evidence_references"] or "[]")
    return DecisionPlanDryRunReport(
        validation_id=row["validation_id"],
        plan_id=row["plan_id"],
        plan_version=row["plan_version"],
        plan_digest=row["plan_digest"],
        review_id=row["review_id"],
        session_id=row["session_id"],
        application_fingerprint=row["application_fingerprint"],
        status=PlanValidationStatus(row["status"]),
        has_warnings=bool(row["has_warnings"]) if "has_warnings" in row.keys() else False,
        approval_stale=bool(row["approval_stale"]),
        checks=[ValidationCheck(**item) for item in checks_raw],
        validated_at=row["validated_at"],
        mode=row["mode"],
        execution_performed=False,
        mutations_performed=False,
        disclaimer=row["disclaimer"],
        evidence_references=[KnowledgeEvidenceReference(**item) for item in refs_raw],
        schema_version=row["schema_version"],
    )


def list_validations_for_plan(plan_id: str) -> List[DecisionPlanDryRunReport]:
    init_decision_validation_store()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM decision_plan_validations
            WHERE plan_id = ?
            ORDER BY validated_at ASC, validation_id ASC
            """,
            (plan_id,),
        ).fetchall()
    return [_row_to_report(row) for row in rows]


def latest_validation_for_plan(plan_id: str) -> Optional[DecisionPlanDryRunReport]:
    init_decision_validation_store()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM decision_plan_validations
            WHERE plan_id = ?
            ORDER BY validated_at DESC, validation_id DESC
            LIMIT 1
            """,
            (plan_id,),
        ).fetchone()
    return _row_to_report(row) if row else None


def new_validation_id() -> str:
    return str(uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
