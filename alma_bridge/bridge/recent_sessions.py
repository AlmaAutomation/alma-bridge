"""Read-only recent session summaries for Compatibility Explorer."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from alma_bridge.schemas.models import RecentSessionItem, RecentSessionsResponse
from alma_bridge.session.stop_on_success_verification import aggregate_verification_passed
from alma_bridge.storage import outcomes

logger = logging.getLogger(__name__)

_MAX_LIMIT = 100


def _application_name(file_path: Optional[str]) -> str:
    if not file_path:
        return "Unknown application"
    name = Path(str(file_path)).name
    return name or str(file_path)


def _session_state(row: Dict[str, Any]) -> str:
    raw = row.get("session_state")
    if raw:
        return str(raw).upper()
    if not row.get("finished_at"):
        return "RUNNING"
    return "SUCCEEDED" if bool(row.get("success")) else "FAILED"


def _graph_compatible(fingerprint: Optional[str]) -> bool:
    return bool(fingerprint and str(fingerprint).strip())


def _load_authoritative_verification_flags(session_ids: List[str]) -> Dict[str, bool]:
    if not session_ids:
        return {}
    flags: Dict[str, bool] = {}
    with outcomes._connect() as conn:  # noqa: SLF001 — read-only batch lookup
        placeholders = ",".join("?" for _ in session_ids)
        rows = conn.execute(
            f"""
            SELECT session_id, success, verification_json
            FROM bridge_attempts
            WHERE session_id IN ({placeholders})
            ORDER BY attempt_number ASC
            """,
            session_ids,
        ).fetchall()
    for row in rows:
        session_id = str(row["session_id"])
        if flags.get(session_id):
            continue
        if int(row["success"] or 0) != 1:
            continue
        raw = row["verification_json"]
        if not raw:
            continue
        try:
            verification = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            continue
        if aggregate_verification_passed({"verification": verification}):
            flags[session_id] = True
    return flags


def serialize_recent_session_row(
    row: Dict[str, Any],
    *,
    verified: bool,
) -> Optional[RecentSessionItem]:
    """Map one persisted session row to explorer metadata; return None when malformed."""
    try:
        session_id = str(row["session_id"])
        fingerprint = row.get("file_hash")
        fingerprint_str = str(fingerprint).strip() if fingerprint else None
        if fingerprint_str == "":
            fingerprint_str = None
        started_at = str(row["started_at"])
        finished_at = row.get("finished_at")
        return RecentSessionItem(
            session_id=session_id,
            application_fingerprint=fingerprint_str,
            application_name=_application_name(row.get("file_path")),
            state=_session_state(row),
            verified=verified,
            started_at=started_at,
            finished_at=str(finished_at) if finished_at else None,
            graph_compatible=_graph_compatible(fingerprint_str),
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("skipping malformed recent session row: %s", exc)
        return None


def build_recent_sessions_response(
    *,
    limit: int = 20,
    file_path: Optional[str] = None,
) -> RecentSessionsResponse:
    bounded = max(1, min(int(limit), _MAX_LIMIT))
    rows = outcomes.list_recent_sessions(limit=bounded, file_path=file_path)
    session_ids = [str(row["session_id"]) for row in rows if row.get("session_id")]
    verified_flags = _load_authoritative_verification_flags(session_ids)

    sessions: List[RecentSessionItem] = []
    for row in rows:
        session_id = str(row.get("session_id") or "")
        item = serialize_recent_session_row(
            row,
            verified=bool(verified_flags.get(session_id)),
        )
        if item is not None:
            sessions.append(item)

    return RecentSessionsResponse(sessions=sessions, count=len(sessions))
