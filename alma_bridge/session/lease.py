from __future__ import annotations

import os
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from alma_bridge.config import settings
from alma_bridge.storage import outcomes


def _default_owner_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


@dataclass
class SessionLease:
    session_id: str
    owner_id: str
    expires_at: str
    acquired: bool = False


class SessionLeaseManager:
    """DB-backed lease so only one worker drives a session lifecycle."""

    DEFAULT_LEASE_SEC = 300

    def __init__(self, owner_id: Optional[str] = None) -> None:
        self.owner_id = owner_id or _default_owner_id()

    def acquire(
        self,
        session_id: str,
        *,
        lease_sec: Optional[int] = None,
        renew: bool = True,
    ) -> SessionLease:
        duration = lease_sec or getattr(settings, "session_lease_sec", self.DEFAULT_LEASE_SEC)
        expires = datetime.now(timezone.utc) + timedelta(seconds=max(1, duration))
        ok = outcomes.acquire_session_lease(
            session_id,
            owner_id=self.owner_id,
            expires_at=expires.isoformat(),
            renew=renew,
        )
        return SessionLease(
            session_id=session_id,
            owner_id=self.owner_id,
            expires_at=expires.isoformat(),
            acquired=ok,
        )

    def renew(self, session_id: str, *, lease_sec: Optional[int] = None) -> bool:
        duration = lease_sec or getattr(settings, "session_lease_sec", self.DEFAULT_LEASE_SEC)
        expires = datetime.now(timezone.utc) + timedelta(seconds=max(1, duration))
        return outcomes.renew_session_lease(
            session_id,
            owner_id=self.owner_id,
            expires_at=expires.isoformat(),
        )

    def release(self, session_id: str) -> None:
        outcomes.release_session_lease(session_id, owner_id=self.owner_id)

    def holds_lease(self, session_id: str) -> bool:
        return outcomes.session_lease_owner(session_id) == self.owner_id
