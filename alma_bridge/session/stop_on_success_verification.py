"""Authoritative verification checks for stop-on-success short-circuit."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from alma_bridge.schemas.models import AttemptRecord


def aggregate_verification_passed(payload: Mapping[str, Any]) -> bool:
    """True only when persisted aggregate verification explicitly passed."""
    verification = payload.get("verification")
    if not isinstance(verification, Mapping):
        return False
    return verification.get("passed") is True


def attempt_row_authorizes_stop(row: Any) -> bool:
    """Fail closed: only success=True rows with verification.passed=True qualify."""
    if not isinstance(row, Mapping):
        return False
    if row.get("success") is not True:
        return False
    return aggregate_verification_passed(row)


def in_memory_attempt_authorizes_stop(record: AttemptRecord) -> bool:
    """In-memory attempt must be successful; verification read from model dump."""
    if not record.success:
        return False
    try:
        payload = record.model_dump()
    except Exception:  # noqa: BLE001
        return False
    return aggregate_verification_passed(payload)


def persisted_session_has_authoritative_verification(
    winning: Optional[AttemptRecord],
    persisted: Mapping[str, Any],
) -> bool:
    """Scan the current session's persisted attempts for authoritative verification."""
    if winning is not None and in_memory_attempt_authorizes_stop(winning):
        return True

    raw_winner = persisted.get("winning_attempt")
    if attempt_row_authorizes_stop(raw_winner):
        return True

    attempts = persisted.get("attempts")
    if not isinstance(attempts, list):
        return False

    for row in attempts:
        if attempt_row_authorizes_stop(row):
            return True
    return False
