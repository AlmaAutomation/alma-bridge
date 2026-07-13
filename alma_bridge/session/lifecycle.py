from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from alma_bridge.session.state import SessionState, validate_transition
from alma_bridge.storage import outcomes


class InvalidSessionTransition(Exception):
    """Raised when a lifecycle transition is illegal or lost a concurrency race."""


@dataclass
class TransitionRecord:
    session_id: str
    correlation_id: str
    previous_state: str
    next_state: str
    timestamp: str
    reason: str
    attempt_number: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class SessionLifecycleManager:
    """Transactional session state machine. Only BridgeOrchestrator should drive this."""

    def __init__(self, session_id: str, *, correlation_id: Optional[str] = None) -> None:
        self.session_id = session_id
        self.correlation_id = correlation_id or session_id
        self._state: Optional[SessionState] = None

    @property
    def state(self) -> SessionState:
        if self._state is None:
            self._state = self._load_state()
        return self._state

    def transition(
        self,
        to: SessionState,
        *,
        reason: str,
        attempt_number: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        expected_from: Optional[SessionState] = None,
    ) -> TransitionRecord:
        current = expected_from or self.state
        if current == to:
            return TransitionRecord(
                session_id=self.session_id,
                correlation_id=self.correlation_id,
                previous_state=current.value,
                next_state=to.value,
                timestamp=datetime.now(timezone.utc).isoformat(),
                reason=reason,
                attempt_number=attempt_number,
                metadata=metadata,
            )
        try:
            validate_transition(current, to)
        except ValueError as exc:
            raise InvalidSessionTransition(str(exc)) from exc

        record = outcomes.transition_session_state(
            session_id=self.session_id,
            correlation_id=self.correlation_id,
            expected_state=current.value,
            next_state=to.value,
            reason=reason,
            attempt_number=attempt_number,
            metadata=metadata,
        )
        if record is None:
            raise InvalidSessionTransition(
                f"Concurrent transition conflict for session {self.session_id}: "
                f"expected {current.value} -> {to.value}"
            )
        self._state = to
        return TransitionRecord(
            session_id=self.session_id,
            correlation_id=self.correlation_id,
            previous_state=record["previous_state"],
            next_state=record["next_state"],
            timestamp=record["timestamp"],
            reason=reason,
            attempt_number=attempt_number,
            metadata=metadata,
        )

    def list_transitions(self, *, limit: int = 100) -> List[Dict[str, Any]]:
        return outcomes.list_session_transitions(self.session_id, limit=limit)

    def _load_state(self) -> SessionState:
        raw = outcomes.get_session_state(self.session_id)
        if not raw:
            return SessionState.CREATED
        try:
            return SessionState(raw)
        except ValueError:
            return SessionState.CREATED
