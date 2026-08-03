"""Append-only SQLite store for decision plan reviews and exports."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from alma_bridge.config import settings
from alma_bridge.decision_review.models import Decision, DecisionPlanArtifact, DecisionPlanReview


def _connect() -> sqlite3.Connection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_decision_review_store() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS decision_plan_reviews (
                review_id TEXT PRIMARY KEY,
                plan_id TEXT NOT NULL,
                application_fingerprint TEXT NOT NULL,
                session_id TEXT,
                plan_version TEXT NOT NULL,
                plan_digest TEXT NOT NULL,
                decision TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                reviewed_at TEXT NOT NULL,
                comment TEXT NOT NULL DEFAULT '',
                risk_acknowledgements TEXT NOT NULL DEFAULT '[]',
                evidence_references TEXT NOT NULL DEFAULT '[]',
                schema_version TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_decision_reviews_plan
                ON decision_plan_reviews(plan_id, reviewed_at);

            CREATE TABLE IF NOT EXISTS decision_plan_exports (
                artifact_id TEXT PRIMARY KEY,
                plan_id TEXT NOT NULL,
                plan_version TEXT NOT NULL,
                plan_digest TEXT NOT NULL,
                format TEXT NOT NULL,
                content TEXT NOT NULL,
                exported_at TEXT NOT NULL,
                disclaimer TEXT NOT NULL,
                execution_status TEXT NOT NULL,
                schema_version TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_decision_exports_plan
                ON decision_plan_exports(plan_id, exported_at);
            """
        )
        conn.commit()


def append_review(review: DecisionPlanReview) -> DecisionPlanReview:
    init_decision_review_store()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO decision_plan_reviews (
                review_id, plan_id, application_fingerprint, session_id,
                plan_version, plan_digest, decision, reviewer, reviewed_at,
                comment, risk_acknowledgements, evidence_references, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review.review_id,
                review.plan_id,
                review.application_fingerprint,
                review.session_id,
                review.plan_version,
                review.plan_digest,
                review.decision.value,
                review.reviewer,
                review.reviewed_at,
                review.comment,
                json.dumps(review.risk_acknowledgements),
                json.dumps(
                    [ref.model_dump(mode="json") for ref in review.evidence_references]
                ),
                review.schema_version,
            ),
        )
        conn.commit()
    return review


def append_export(artifact: DecisionPlanArtifact) -> DecisionPlanArtifact:
    init_decision_review_store()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO decision_plan_exports (
                artifact_id, plan_id, plan_version, plan_digest, format,
                content, exported_at, disclaimer, execution_status, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact.artifact_id,
                artifact.plan_id,
                artifact.plan_version,
                artifact.plan_digest,
                artifact.format,
                artifact.content,
                artifact.exported_at,
                artifact.disclaimer,
                artifact.execution_status,
                artifact.schema_version,
            ),
        )
        conn.commit()
    return artifact


def _row_to_review(row: sqlite3.Row) -> DecisionPlanReview:
    from alma_bridge.knowledge.models import KnowledgeEvidenceReference

    refs_raw = json.loads(row["evidence_references"] or "[]")
    return DecisionPlanReview(
        review_id=row["review_id"],
        plan_id=row["plan_id"],
        application_fingerprint=row["application_fingerprint"],
        session_id=row["session_id"],
        plan_version=row["plan_version"],
        plan_digest=row["plan_digest"],
        decision=Decision(row["decision"]),
        reviewer=row["reviewer"],
        reviewed_at=row["reviewed_at"],
        comment=row["comment"] or "",
        risk_acknowledgements=json.loads(row["risk_acknowledgements"] or "[]"),
        evidence_references=[KnowledgeEvidenceReference(**item) for item in refs_raw],
        schema_version=row["schema_version"],
    )


def list_reviews_for_plan(plan_id: str) -> List[DecisionPlanReview]:
    init_decision_review_store()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM decision_plan_reviews
            WHERE plan_id = ?
            ORDER BY reviewed_at ASC, review_id ASC
            """,
            (plan_id,),
        ).fetchall()
    return [_row_to_review(row) for row in rows]


def latest_review_for_plan(plan_id: str) -> Optional[DecisionPlanReview]:
    init_decision_review_store()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM decision_plan_reviews
            WHERE plan_id = ?
            ORDER BY reviewed_at DESC, review_id DESC
            LIMIT 1
            """,
            (plan_id,),
        ).fetchone()
    return _row_to_review(row) if row else None


def new_review_id() -> str:
    return str(uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
