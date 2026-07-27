"""Repository protocol and read-only outcomes store adapter."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from alma_bridge.compatibility.profile_shadow_store import (
    load_shadow_candidates,
    load_shadow_prediction,
)
from alma_bridge.compatibility.profile_store import (
    _connect as profile_connect,
    load_candidate_for_session_attempt,
)
from alma_bridge.storage import outcomes


@runtime_checkable
class CompatibilityEvidenceRepository(Protocol):
    def get_session_record(self, session_id: str) -> Optional[Dict[str, Any]]: ...

    def list_sessions_for_fingerprint(self, fingerprint: str) -> List[Dict[str, Any]]: ...

    def get_shadow_prediction(self, session_id: str) -> Optional[Dict[str, Any]]: ...

    def get_shadow_candidates(self, shadow_event_id: str) -> List[Dict[str, Any]]: ...

    def get_shadow_comparison(self, session_id: str) -> Optional[Dict[str, Any]]: ...

    def get_profile_candidate_for_attempt(
        self,
        session_id: str,
        attempt_number: int,
    ) -> Optional[Any]: ...


class OutcomesStoreAdapter:
    """Read-only adapter over persisted bridge session and shadow evidence."""

    def get_session_record(self, session_id: str) -> Optional[Dict[str, Any]]:
        return outcomes.get_session(session_id)

    def list_sessions_for_fingerprint(self, fingerprint: str) -> List[Dict[str, Any]]:
        with outcomes._connect() as conn:  # noqa: SLF001 — adapter owns persistence reads
            rows = conn.execute(
                """
                SELECT session_id
                FROM bridge_sessions
                WHERE file_hash = ?
                ORDER BY started_at DESC
                """,
                (fingerprint,),
            ).fetchall()
        sessions: List[Dict[str, Any]] = []
        for row in rows:
            session = outcomes.get_session(str(row["session_id"]))
            if session:
                sessions.append(session)
        return sessions

    def get_shadow_prediction(self, session_id: str) -> Optional[Dict[str, Any]]:
        return load_shadow_prediction(session_id)

    def get_shadow_candidates(self, shadow_event_id: str) -> List[Dict[str, Any]]:
        return load_shadow_candidates(shadow_event_id)

    def get_shadow_comparison(self, session_id: str) -> Optional[Dict[str, Any]]:
        with profile_connect() as conn:
            try:
                row = conn.execute(
                    """
                    SELECT *
                    FROM compatibility_profile_shadow_comparisons
                    WHERE session_id = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (session_id,),
                ).fetchone()
            except sqlite3.OperationalError:
                return None
        if not row:
            return None
        result = dict(row)
        for key in (
            "predicted_remediation_protocol_json",
            "actual_remediation_protocol_json",
            "comparison_metrics_json",
        ):
            raw = result.get(key)
            if isinstance(raw, str):
                try:
                    result[key.replace("_json", "")] = json.loads(raw or "null")
                except json.JSONDecodeError:
                    result[key.replace("_json", "")] = None
        return result

    def get_profile_candidate_for_attempt(
        self,
        session_id: str,
        attempt_number: int,
    ) -> Optional[Any]:
        return load_candidate_for_session_attempt(session_id, attempt_number)
