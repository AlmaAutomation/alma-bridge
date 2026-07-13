from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from alma_bridge.compatibility.profile_store import insert_invalidation

logger = logging.getLogger(__name__)

_COUNTERS: Dict[str, int] = {}


def increment_profile_counter(name: str, *, amount: int = 1) -> None:
    _COUNTERS[name] = _COUNTERS.get(name, 0) + amount


def get_profile_counters() -> Dict[str, int]:
    return dict(_COUNTERS)


def reset_profile_counters() -> None:
    _COUNTERS.clear()


def log_profile_event(event: str, **fields: Any) -> None:
    logger.info("compatibility_profile.%s %s", event, fields)


class ProfileInvalidationRepository:
    """Scoped invalidation records for compatibility profiles (Phase 1 storage only)."""

    def record(
        self,
        *,
        profile_id: str,
        scope: str,
        scope_key: str,
        rule_id: str,
        reason: str,
        evidence: Optional[Dict[str, Any]] = None,
    ) -> str:
        invalidation_id = insert_invalidation(
            profile_id=profile_id,
            scope=scope,
            scope_key=scope_key,
            rule_id=rule_id,
            reason=reason,
            evidence=evidence,
        )
        increment_profile_counter("profile_invalidation_recorded")
        log_profile_event(
            "invalidation_recorded",
            profile_id=profile_id,
            scope=scope,
            rule_id=rule_id,
            invalidation_id=invalidation_id,
        )
        return invalidation_id

    def list_active(
        self,
        profile_id: str,
        *,
        scope: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        from alma_bridge.compatibility.profile_store import _connect, ensure_profile_tables

        with _connect() as conn:
            ensure_profile_tables(conn)
            if scope:
                rows = conn.execute(
                    """
                    SELECT * FROM compatibility_profile_invalidations
                    WHERE profile_id = ? AND scope = ? AND active = 1
                    ORDER BY created_at DESC
                    """,
                    (profile_id, scope),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM compatibility_profile_invalidations
                    WHERE profile_id = ? AND active = 1
                    ORDER BY created_at DESC
                    """,
                    (profile_id,),
                ).fetchall()
        return [dict(row) for row in rows]
