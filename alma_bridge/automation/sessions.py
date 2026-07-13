"""Automation session store — audit trail for full-machine automation runs."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from alma_bridge.config import settings


def _connect() -> sqlite3.Connection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_automation_store() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS automation_sessions (
                session_id TEXT PRIMARY KEY,
                hostname TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                success INTEGER NOT NULL DEFAULT 0,
                verdict TEXT,
                potato_score INTEGER,
                summary TEXT,
                phases TEXT,
                request TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_automation_started ON automation_sessions(started_at);

            CREATE TABLE IF NOT EXISTS automation_approvals (
                token TEXT PRIMARY KEY,
                step_ids TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                used_at TEXT
            );

            CREATE TABLE IF NOT EXISTS automation_agents (
                agent_id TEXT PRIMARY KEY,
                hostname TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                capabilities TEXT,
                meta TEXT
            );
            """
        )
        conn.commit()


def new_automation_session(
    *,
    hostname: str,
    request: Dict[str, Any],
) -> str:
    init_automation_store()
    session_id = str(uuid4())
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO automation_sessions (
                session_id, hostname, started_at, success, request
            ) VALUES (?, ?, ?, 0, ?)
            """,
            (
                session_id,
                hostname,
                datetime.now(timezone.utc).isoformat(),
                json.dumps(request),
            ),
        )
        conn.commit()
    return session_id


def finalize_automation_session(
    session_id: str,
    *,
    success: bool,
    verdict: Optional[str],
    potato_score: Optional[int],
    summary: str,
    phases: List[Dict[str, Any]],
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE automation_sessions
            SET finished_at = ?, success = ?, verdict = ?, potato_score = ?,
                summary = ?, phases = ?
            WHERE session_id = ?
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                int(success),
                verdict,
                potato_score,
                summary,
                json.dumps(phases),
                session_id,
            ),
        )
        conn.commit()


def get_automation_session(session_id: str) -> Optional[Dict[str, Any]]:
    init_automation_store()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM automation_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    if not row:
        return None
    data = dict(row)
    data["success"] = bool(data.get("success"))
    data["phases"] = json.loads(data.get("phases") or "[]")
    data["request"] = json.loads(data.get("request") or "{}")
    return data


def list_automation_sessions(*, limit: int = 20) -> List[Dict[str, Any]]:
    init_automation_store()
    limit = max(1, min(int(limit), 100))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT session_id, hostname, started_at, finished_at, success,
                   verdict, potato_score, summary
            FROM automation_sessions
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
