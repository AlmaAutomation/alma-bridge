"""Online feedback store for the compliance autopilot.

Records which remediation *pathway* worked for which error *signature* so the
autopilot can re-rank pathways over time (a lightweight, transparent bandit:
Laplace-smoothed success rate, no opaque model). Stored in the same SQLite DB
as bridge outcomes, in its own table so it never collides with the execution
learning schema.
"""

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


def init_healing_store() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS compliance_pathway_feedback (
                signature TEXT NOT NULL,
                pathway_id TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                successes INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT,
                PRIMARY KEY (signature, pathway_id)
            );
            """
        )
        conn.commit()


def record_pathway_outcome(signature: str, pathway_id: str, success: bool) -> None:
    init_healing_store()
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO compliance_pathway_feedback (
                signature, pathway_id, attempts, successes, updated_at
            ) VALUES (?, ?, 1, ?, ?)
            ON CONFLICT(signature, pathway_id) DO UPDATE SET
                attempts = attempts + 1,
                successes = successes + ?,
                updated_at = ?
            """,
            (signature, pathway_id, int(success), now, int(success), now),
        )
        conn.commit()


def pathway_scores(signature: str) -> Dict[str, Dict[str, float]]:
    """Return ``{pathway_id: {attempts, successes, rate}}`` for a signature.

    ``rate`` is Laplace-smoothed (``(s+1)/(a+2)``) so a single lucky success
    doesn't dominate and unseen pathways start at a neutral 0.5.
    """
    init_healing_store()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT pathway_id, attempts, successes
            FROM compliance_pathway_feedback
            WHERE signature = ?
            """,
            (signature,),
        ).fetchall()
    scores: Dict[str, Dict[str, float]] = {}
    for row in rows:
        attempts = int(row["attempts"] or 0)
        successes = int(row["successes"] or 0)
        scores[row["pathway_id"]] = {
            "attempts": attempts,
            "successes": successes,
            "rate": round((successes + 1) / (attempts + 2), 4),
        }
    return scores


def feedback_summary(limit: int = 50) -> List[Dict[str, object]]:
    init_healing_store()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT signature, pathway_id, attempts, successes, updated_at
            FROM compliance_pathway_feedback
            ORDER BY attempts DESC, updated_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    out: List[Dict[str, object]] = []
    for row in rows:
        attempts = int(row["attempts"] or 0)
        successes = int(row["successes"] or 0)
        out.append(
            {
                "signature": row["signature"],
                "pathway_id": row["pathway_id"],
                "attempts": attempts,
                "successes": successes,
                "smoothed_rate": round((successes + 1) / (attempts + 2), 4),
                "updated_at": row["updated_at"],
            }
        )
    return out
