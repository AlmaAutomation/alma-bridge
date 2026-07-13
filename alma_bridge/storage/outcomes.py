from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from alma_bridge.config import settings


def _connect() -> sqlite3.Connection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    _ensure_session_columns(conn)
    return conn


def init_outcome_store() -> None:
    from alma_bridge.compatibility.profile_shadow import init_profile_shadow_infrastructure
    from alma_bridge.compatibility.profile_store import init_profile_store

    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS bridge_sessions (
                session_id TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                file_hash TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                success INTEGER NOT NULL DEFAULT 0,
                hardware_profile TEXT,
                summary TEXT,
                rerank_events TEXT
            );

            CREATE TABLE IF NOT EXISTS bridge_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                strategy_id TEXT NOT NULL,
                remediation_id TEXT,
                runtime TEXT NOT NULL,
                command TEXT NOT NULL,
                env TEXT,
                mode TEXT NOT NULL,
                success INTEGER NOT NULL,
                exit_code INTEGER,
                error_signature TEXT,
                detected_error TEXT,
                stdout TEXT,
                stderr TEXT,
                duration_ms INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES bridge_sessions(session_id)
            );

            CREATE INDEX IF NOT EXISTS idx_attempts_session ON bridge_attempts(session_id);
            CREATE INDEX IF NOT EXISTS idx_attempts_signature ON bridge_attempts(error_signature);
            CREATE INDEX IF NOT EXISTS idx_attempts_strategy ON bridge_attempts(strategy_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_path ON bridge_sessions(file_path);

            CREATE TABLE IF NOT EXISTS import_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                source_key TEXT NOT NULL UNIQUE,
                session_id TEXT NOT NULL,
                imported_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
    init_profile_store()
    init_profile_shadow_infrastructure()


_SESSION_COLUMN_MIGRATIONS = {
    "rerank_events": "TEXT",
    "session_state": "TEXT NOT NULL DEFAULT 'CREATED'",
    "parent_session_id": "TEXT",
    "correlation_id": "TEXT",
    "inspection_json": "TEXT",
    "policy_context_json": "TEXT",
    "escalation_json": "TEXT",
    "session_timeout_at": "TEXT",
    "lease_owner_id": "TEXT",
    "lease_expires_at": "TEXT",
}

_ATTEMPT_COLUMN_MIGRATIONS = {
    "phase": "TEXT NOT NULL DEFAULT 'run'",
    "parent_attempt_number": "INTEGER",
    "route_id": "TEXT",
    "policy_decision_json": "TEXT",
    "verification_json": "TEXT",
    "state_fingerprint": "TEXT",
    "escalation_kind": "TEXT",
}


def _ensure_session_columns(conn: sqlite3.Connection) -> None:
    table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='bridge_sessions'"
    ).fetchone()
    if not table:
        return
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(bridge_sessions)").fetchall()
    }
    changed = False
    for name, ddl in _SESSION_COLUMN_MIGRATIONS.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE bridge_sessions ADD COLUMN {name} {ddl}")
            changed = True
    if changed:
        conn.commit()

    attempt_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='bridge_attempts'"
    ).fetchone()
    if attempt_table:
        attempt_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(bridge_attempts)").fetchall()
        }
        attempt_changed = False
        for name, ddl in _ATTEMPT_COLUMN_MIGRATIONS.items():
            if name not in attempt_columns:
                conn.execute(f"ALTER TABLE bridge_attempts ADD COLUMN {name} {ddl}")
                attempt_changed = True
        if attempt_changed:
            conn.commit()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bridge_session_transitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            correlation_id TEXT NOT NULL,
            previous_state TEXT NOT NULL,
            next_state TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            reason TEXT,
            attempt_number INTEGER,
            metadata_json TEXT,
            FOREIGN KEY(session_id) REFERENCES bridge_sessions(session_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_transitions_session
        ON bridge_session_transitions(session_id)
        """
    )
    conn.commit()


def new_session(
    file_path: str,
    file_hash: Optional[str],
    hardware_profile: Dict[str, Any],
    *,
    parent_session_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    session_timeout_at: Optional[str] = None,
) -> str:
    session_id = str(uuid4())
    corr = correlation_id or session_id
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO bridge_sessions (
                session_id, file_path, file_hash, started_at, success, hardware_profile,
                session_state, parent_session_id, correlation_id, session_timeout_at
            ) VALUES (?, ?, ?, ?, 0, ?, 'CREATED', ?, ?, ?)
            """,
            (
                session_id,
                file_path,
                file_hash,
                datetime.now(timezone.utc).isoformat(),
                json.dumps(hardware_profile),
                parent_session_id,
                corr,
                session_timeout_at,
            ),
        )
        conn.execute(
            """
            INSERT INTO bridge_session_transitions (
                session_id, correlation_id, previous_state, next_state, timestamp, reason
            ) VALUES (?, ?, 'NONE', 'CREATED', ?, 'session_created')
            """,
            (
                session_id,
                corr,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    return session_id


def get_session_state(session_id: str) -> Optional[str]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT session_state FROM bridge_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return row["session_state"] if row else None


def transition_session_state(
    *,
    session_id: str,
    correlation_id: str,
    expected_state: str,
    next_state: str,
    reason: str,
    attempt_number: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Atomically validate, record transition, and update session state."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT session_state FROM bridge_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row or row["session_state"] != expected_state:
            conn.execute("ROLLBACK")
            return None
        updated = conn.execute(
            """
            UPDATE bridge_sessions
            SET session_state = ?
            WHERE session_id = ? AND session_state = ?
            """,
            (next_state, session_id, expected_state),
        )
        if updated.rowcount != 1:
            conn.execute("ROLLBACK")
            return None
        conn.execute(
            """
            INSERT INTO bridge_session_transitions (
                session_id, correlation_id, previous_state, next_state,
                timestamp, reason, attempt_number, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                correlation_id,
                expected_state,
                next_state,
                now,
                reason,
                attempt_number,
                json.dumps(metadata or {}),
            ),
        )
        conn.commit()
    return {
        "previous_state": expected_state,
        "next_state": next_state,
        "timestamp": now,
    }


def list_session_transitions(session_id: str, *, limit: int = 100) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM bridge_session_transitions
            WHERE session_id = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (session_id, max(1, min(limit, 500))),
        ).fetchall()
    result: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json", None) or "{}")
        result.append(item)
    return result


def acquire_session_lease(
    session_id: str,
    *,
    owner_id: str,
    expires_at: str,
    renew: bool = True,
) -> bool:
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT lease_owner_id, lease_expires_at
            FROM bridge_sessions WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        if not row:
            conn.execute("ROLLBACK")
            return False
        current_owner = row["lease_owner_id"]
        current_expires = row["lease_expires_at"]
        expired = True
        if current_expires:
            try:
                exp_dt = datetime.fromisoformat(current_expires.replace("Z", "+00:00"))
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                expired = exp_dt <= now_dt
            except ValueError:
                expired = current_expires <= now
        if current_owner and current_owner != owner_id and not expired:
            conn.execute("ROLLBACK")
            return False
        if current_owner == owner_id and not renew:
            conn.execute("ROLLBACK")
            return True
        updated = conn.execute(
            """
            UPDATE bridge_sessions
            SET lease_owner_id = ?, lease_expires_at = ?
            WHERE session_id = ?
            """,
            (owner_id, expires_at, session_id),
        )
        if updated.rowcount != 1:
            conn.execute("ROLLBACK")
            return False
        conn.commit()
    return True


def renew_session_lease(session_id: str, *, owner_id: str, expires_at: str) -> bool:
    with _connect() as conn:
        updated = conn.execute(
            """
            UPDATE bridge_sessions
            SET lease_expires_at = ?
            WHERE session_id = ? AND lease_owner_id = ?
            """,
            (expires_at, session_id, owner_id),
        )
        conn.commit()
        return updated.rowcount == 1


def release_session_lease(session_id: str, *, owner_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE bridge_sessions
            SET lease_owner_id = NULL, lease_expires_at = NULL
            WHERE session_id = ? AND lease_owner_id = ?
            """,
            (session_id, owner_id),
        )
        conn.commit()


def session_lease_owner(session_id: str) -> Optional[str]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT lease_owner_id, lease_expires_at FROM bridge_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    if not row:
        return None
    owner = row["lease_owner_id"]
    expires = row["lease_expires_at"]
    if not owner:
        return None
    if expires:
        try:
            exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if exp_dt <= datetime.now(timezone.utc):
                return None
        except ValueError:
            if expires <= datetime.now(timezone.utc).isoformat():
                return None
    return owner


def update_session_inspection(session_id: str, inspection: Dict[str, Any]) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE bridge_sessions SET inspection_json = ? WHERE session_id = ?",
            (json.dumps(inspection), session_id),
        )
        conn.commit()


def update_session_escalation(session_id: str, escalation: Dict[str, Any]) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE bridge_sessions SET escalation_json = ? WHERE session_id = ?",
            (json.dumps(escalation), session_id),
        )
        conn.commit()


def record_attempt(
    *,
    session_id: str,
    attempt_number: int,
    strategy_id: str,
    remediation_id: Optional[str],
    runtime: str,
    command: List[str],
    env: Dict[str, str],
    mode: str,
    success: bool,
    exit_code: Optional[int],
    error_signature: Optional[str],
    detected_error: Optional[str],
    stdout: str,
    stderr: str,
    duration_ms: int,
    phase: str = "run",
    parent_attempt_number: Optional[int] = None,
    route_id: Optional[str] = None,
    policy_decision: Optional[Dict[str, Any]] = None,
    verification: Optional[Dict[str, Any]] = None,
    state_fingerprint: Optional[str] = None,
    escalation_kind: Optional[str] = None,
) -> int:
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO bridge_attempts (
                session_id, attempt_number, strategy_id, remediation_id, runtime,
                command, env, mode, success, exit_code, error_signature, detected_error,
                stdout, stderr, duration_ms, created_at, phase, parent_attempt_number,
                route_id, policy_decision_json, verification_json, state_fingerprint,
                escalation_kind
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                attempt_number,
                strategy_id,
                remediation_id,
                runtime,
                json.dumps(command),
                json.dumps(env),
                mode,
                int(success),
                exit_code,
                error_signature,
                detected_error,
                stdout,
                stderr,
                duration_ms,
                datetime.now(timezone.utc).isoformat(),
                phase,
                parent_attempt_number,
                route_id,
                json.dumps(policy_decision or {}),
                json.dumps(verification or {}),
                state_fingerprint,
                escalation_kind,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def update_session_progress(session_id: str, summary: str) -> None:
    """Write live progress into an in-flight session (summary until finalize)."""
    with _connect() as conn:
        conn.execute(
            "UPDATE bridge_sessions SET summary = ? WHERE session_id = ? AND finished_at IS NULL",
            (summary, session_id),
        )
        conn.commit()


def finalize_session(
    session_id: str,
    success: bool,
    summary: str,
    *,
    rerank_events: Optional[List[Dict[str, Any]]] = None,
) -> None:
    with _connect() as conn:
        _ensure_session_columns(conn)
        conn.execute(
            """
            UPDATE bridge_sessions
            SET finished_at = ?, success = ?, summary = ?, rerank_events = ?
            WHERE session_id = ?
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                int(success),
                summary,
                json.dumps(rerank_events or []),
                session_id,
            ),
        )
        conn.commit()


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        session = conn.execute(
            "SELECT * FROM bridge_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not session:
            return None

        attempts = conn.execute(
            """
            SELECT * FROM bridge_attempts
            WHERE session_id = ?
            ORDER BY attempt_number ASC
            """,
            (session_id,),
        ).fetchall()

    result = dict(session)
    result["hardware_profile"] = json.loads(result.get("hardware_profile") or "{}")
    result["rerank_events"] = json.loads(result.get("rerank_events") or "[]")
    result["attempts"] = [_deserialize_attempt(dict(row)) for row in attempts]
    winning = next((attempt for attempt in reversed(result["attempts"]) if attempt.get("success")), None)
    result["winning_attempt"] = winning
    return result


_SESSION_LIST_SELECT = """
    SELECT
        s.session_id,
        s.file_path,
        s.started_at,
        s.finished_at,
        s.success,
        s.summary,
        (
            SELECT COUNT(*)
            FROM bridge_attempts a
            WHERE a.session_id = s.session_id
        ) AS attempt_count,
        (
            SELECT a.strategy_id
            FROM bridge_attempts a
            WHERE a.session_id = s.session_id AND a.success = 1
            ORDER BY a.attempt_number DESC
            LIMIT 1
        ) AS winning_strategy_id,
        (
            SELECT a.remediation_id
            FROM bridge_attempts a
            WHERE a.session_id = s.session_id AND a.success = 1
            ORDER BY a.attempt_number DESC
            LIMIT 1
        ) AS winning_remediation_id,
        s.rerank_events
    FROM bridge_sessions s
"""


def list_recent_sessions(
    *,
    limit: int = 20,
    file_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    with _connect() as conn:
        if file_path:
            rows = conn.execute(
                f"""
                {_SESSION_LIST_SELECT}
                WHERE s.file_path = ?
                ORDER BY s.started_at DESC
                LIMIT ?
                """,
                (file_path, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""
                {_SESSION_LIST_SELECT}
                ORDER BY s.started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    sessions: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        events = json.loads(item.pop("rerank_events", None) or "[]")
        item["rerank_count"] = len(events)
        sessions.append(item)
    return sessions


def _path_session_stats(conn: sqlite3.Connection, file_path: str) -> tuple[int, int, float]:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS successes
        FROM bridge_sessions
        WHERE file_path = ?
        """,
        (file_path,),
    ).fetchone()
    total = int(row["total"] or 0)
    successes = int(row["successes"] or 0)
    rate = round(successes / total, 4) if total else 0.0
    return total, successes, rate


def get_prior_success(file_path: str) -> Dict[str, Any]:
    with _connect() as conn:
        total, successes, rate = _path_session_stats(conn, file_path)
        rows = conn.execute(
            """
            SELECT session_id, finished_at, summary
            FROM bridge_sessions
            WHERE file_path = ? AND success = 1
            ORDER BY finished_at DESC
            LIMIT 5
            """,
            (file_path,),
        ).fetchall()

        session = None
        for row in rows:
            summary = (row["summary"] or "").lower()
            if "launcher detached" in summary and "is running from the install directory" not in summary:
                continue
            if "skipped re-running the installer" in summary and "launcher handoff complete" not in summary:
                continue
            session = row
            break

        if not session:
            return {
                "file_path": file_path,
                "found": False,
                "session_id": None,
                "finished_at": None,
                "strategy_id": None,
                "remediation_id": None,
                "runtime": None,
                "total_sessions": total,
                "successful_sessions": successes,
                "success_rate_for_path": rate,
                "verified": False,
            }

        attempt = conn.execute(
            """
            SELECT strategy_id, remediation_id, runtime
            FROM bridge_attempts
            WHERE session_id = ? AND success = 1
            ORDER BY attempt_number DESC
            LIMIT 1
            """,
            (session["session_id"],),
        ).fetchone()

    attempt_data = dict(attempt) if attempt else {}
    summary_lower = (session["summary"] or "").lower()
    verified = any(
        marker in summary_lower
        for marker in (
            "is running from the install directory",
            "sidecar handoff verified",
            "verified: installed launcher",
            "launcher handoff complete",
        )
    )
    if "skipped re-running the installer" in summary_lower and "launcher handoff complete" not in summary_lower:
        verified = False
    try:
        full = get_session(session["session_id"])
        if full:
            for att in full.get("attempts") or []:
                if not att.get("success") or att.get("phase") != "launcher":
                    continue
                stderr = (att.get("stderr") or "").lower()
                if "is running from the install directory" in stderr:
                    verified = True
    except Exception:  # noqa: BLE001
        pass
    return {
        "file_path": file_path,
        "found": True,
        "session_id": session["session_id"],
        "finished_at": session["finished_at"],
        "strategy_id": attempt_data.get("strategy_id"),
        "remediation_id": attempt_data.get("remediation_id"),
        "runtime": attempt_data.get("runtime"),
        "total_sessions": total,
        "successful_sessions": successes,
        "success_rate_for_path": rate,
        "verified": verified,
    }


def get_stats() -> Dict[str, Any]:
    with _connect() as conn:
        totals = conn.execute(
            """
            SELECT
                COUNT(*) AS total_attempts,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS total_successes
            FROM bridge_attempts
            """
        ).fetchone()

        signatures = conn.execute(
            """
            SELECT error_signature, COUNT(*) AS count
            FROM bridge_attempts
            WHERE error_signature IS NOT NULL
            GROUP BY error_signature
            ORDER BY count DESC
            LIMIT 10
            """
        ).fetchall()

        strategies = conn.execute(
            """
            SELECT strategy_id,
                   COUNT(*) AS attempts,
                   SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS successes
            FROM bridge_attempts
            GROUP BY strategy_id
            ORDER BY attempts DESC
            LIMIT 10
            """
        ).fetchall()

    total_attempts = int(totals["total_attempts"] or 0)
    total_successes = int(totals["total_successes"] or 0)
    total_failures = total_attempts - total_successes
    success_rate = (total_successes / total_attempts) if total_attempts else 0.0

    return {
        "total_attempts": total_attempts,
        "total_successes": total_successes,
        "total_failures": total_failures,
        "success_rate": round(success_rate, 4),
        "top_signatures": [dict(row) for row in signatures],
        "top_strategies": [
            {
                **dict(row),
                "success_rate": round((row["successes"] or 0) / row["attempts"], 4)
                if row["attempts"]
                else 0.0,
            }
            for row in strategies
        ],
    }


def is_imported(source: str, source_key: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM import_log WHERE source = ? AND source_key = ?",
            (source, source_key),
        ).fetchone()
    return row is not None


def mark_imported(source: str, source_key: str, session_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO import_log (source, source_key, session_id, imported_at)
            VALUES (?, ?, ?, ?)
            """,
            (source, source_key, session_id, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def import_session(
    *,
    file_path: str,
    file_hash: Optional[str],
    started_at: Optional[str],
    finished_at: Optional[str],
    success: bool,
    hardware_profile: Dict[str, Any],
    summary: str,
    source: str,
) -> str:
    session_id = f"{source}-{uuid4()}"
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO bridge_sessions (
                session_id, file_path, file_hash, started_at, finished_at,
                success, hardware_profile, summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                file_path,
                file_hash,
                started_at or datetime.now(timezone.utc).isoformat(),
                finished_at,
                int(success),
                json.dumps(hardware_profile),
                summary,
            ),
        )
        conn.commit()
    return session_id


def import_attempt(
    *,
    session_id: str,
    attempt_number: int,
    strategy_id: str,
    remediation_id: Optional[str],
    runtime: str,
    command: List[str],
    env: Dict[str, str],
    mode: str,
    success: bool,
    exit_code: Optional[int],
    error_signature: Optional[str],
    detected_error: Optional[str],
    stdout: str,
    stderr: str,
    duration_ms: int,
    created_at: Optional[str] = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO bridge_attempts (
                session_id, attempt_number, strategy_id, remediation_id, runtime,
                command, env, mode, success, exit_code, error_signature, detected_error,
                stdout, stderr, duration_ms, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                attempt_number,
                strategy_id,
                remediation_id,
                runtime,
                json.dumps(command),
                json.dumps(env),
                mode,
                int(success),
                exit_code,
                error_signature,
                detected_error,
                stdout,
                stderr,
                duration_ms,
                created_at or datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()


def strategy_success_rates() -> Dict[str, float]:
    return _strategy_rates_query()


def strategy_success_rates_for_signature(error_signature: Optional[str]) -> Dict[str, float]:
    """Blend global strategy rates with signature-specific outcomes when available."""
    global_rates = strategy_success_rates()
    if not error_signature:
        return global_rates

    signature_rates = _strategy_rates_query(error_signature=error_signature)
    if not signature_rates:
        return global_rates

    blended = dict(global_rates)
    for strategy_id, rate in signature_rates.items():
        blended[strategy_id] = rate
    return blended


def _strategy_rates_query(*, error_signature: Optional[str] = None) -> Dict[str, float]:
    query = """
        SELECT strategy_id,
               SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS successes,
               COUNT(*) AS attempts
        FROM bridge_attempts
    """
    params: tuple = ()
    if error_signature:
        query += " WHERE error_signature = ?"
        params = (error_signature,)
    query += " GROUP BY strategy_id"

    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()

    rates: Dict[str, float] = {}
    for row in rows:
        attempts = row["attempts"] or 0
        if attempts:
            rates[row["strategy_id"]] = (row["successes"] or 0) / attempts
    return rates


def _deserialize_attempt(row: Dict[str, Any]) -> Dict[str, Any]:
    row["command"] = json.loads(row.get("command") or "[]")
    row["env"] = json.loads(row.get("env") or "{}")
    row["success"] = bool(row.get("success"))
    row["policy_decision"] = json.loads(row.pop("policy_decision_json", None) or "{}")
    row["verification"] = json.loads(row.pop("verification_json", None) or "{}")
    return row
