"""Online learning for Bridge remediation actions per error signature."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Dict, List

from alma_bridge.config import settings


def _connect() -> sqlite3.Connection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_remediation_store() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS bridge_remediation_feedback (
                signature TEXT NOT NULL,
                remediation_id TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                successes INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT,
                PRIMARY KEY (signature, remediation_id)
            );
            """
        )
        conn.commit()


def record_remediation_outcome(
    signature: str,
    remediation_id: str | None,
    success: bool,
) -> None:
    if not remediation_id:
        return
    init_remediation_store()
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO bridge_remediation_feedback (
                signature, remediation_id, attempts, successes, updated_at
            ) VALUES (?, ?, 1, ?, ?)
            ON CONFLICT(signature, remediation_id) DO UPDATE SET
                attempts = attempts + 1,
                successes = successes + ?,
                updated_at = ?
            """,
            (signature, remediation_id, int(success), now, int(success), now),
        )
        conn.commit()


def remediation_scores(signature: str) -> Dict[str, Dict[str, float]]:
    init_remediation_store()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT remediation_id, attempts, successes
            FROM bridge_remediation_feedback
            WHERE signature = ?
            """,
            (signature or "unknown_error",),
        ).fetchall()
    scores: Dict[str, Dict[str, float]] = {}
    for row in rows:
        attempts = int(row["attempts"] or 0)
        successes = int(row["successes"] or 0)
        scores[row["remediation_id"]] = {
            "attempts": attempts,
            "successes": successes,
            "rate": round((successes + 1) / (attempts + 2), 4),
        }
    return scores


def feedback_summary(limit: int = 50) -> List[Dict[str, object]]:
    init_remediation_store()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT signature, remediation_id, attempts, successes, updated_at
            FROM bridge_remediation_feedback
            ORDER BY attempts DESC, updated_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    return [
        {
            "signature": row["signature"],
            "remediation_id": row["remediation_id"],
            "attempts": int(row["attempts"] or 0),
            "successes": int(row["successes"] or 0),
            "smoothed_rate": round(
                (int(row["successes"] or 0) + 1) / (int(row["attempts"] or 0) + 2), 4
            ),
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]
