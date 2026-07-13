"""One-time approval tokens for mutating automation steps."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from alma_bridge.automation.sessions import _connect, init_automation_store


def create_approval_token(
    step_ids: List[str],
    *,
    ttl_minutes: int = 30,
) -> Dict[str, Any]:
    init_automation_store()
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=max(1, min(ttl_minutes, 1440)))
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO automation_approvals (token, step_ids, created_at, expires_at, used)
            VALUES (?, ?, ?, ?, 0)
            """,
            (token, json.dumps(step_ids), now.isoformat(), expires.isoformat()),
        )
        conn.commit()
    return {
        "token": token,
        "step_ids": step_ids,
        "expires_at": expires.isoformat(),
        "ttl_minutes": ttl_minutes,
    }


def consume_approval_token(token: str, step_ids: Optional[List[str]] = None) -> tuple[bool, str]:
    """Validate and mark token used. Optional ``step_ids`` must be subset of token scope."""
    init_automation_store()
    if not token or not token.strip():
        return False, "approval token required"
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM automation_approvals WHERE token = ?",
            (token.strip(),),
        ).fetchone()
        if not row:
            return False, "invalid approval token"
        if row["used"]:
            return False, "approval token already used"
        expires = datetime.fromisoformat(row["expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires:
            return False, "approval token expired"
        allowed = set(json.loads(row["step_ids"] or "[]"))
        if step_ids:
            if not set(step_ids).issubset(allowed):
                return False, "token not valid for requested steps"
        conn.execute(
            "UPDATE automation_approvals SET used = 1, used_at = ? WHERE token = ?",
            (datetime.now(timezone.utc).isoformat(), token.strip()),
        )
        conn.commit()
    return True, ""
