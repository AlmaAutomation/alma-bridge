"""Append-only status transitions with validation."""

from __future__ import annotations

import uuid
from typing import Dict, Optional, Set

from alma_bridge.native_lab.digest import digest_of
from alma_bridge.native_lab.errors import InvalidStatusTransitionError
from alma_bridge.native_lab.models import StatusEvent, WorkItemStatus
from alma_bridge.native_lab.completion import validate_completion_gates as _validate_completion_gates

# Valid forward transitions (planning only — blocked/rejected have special rules)
VALID_TRANSITIONS: Dict[WorkItemStatus, Set[WorkItemStatus]] = {
    WorkItemStatus.PROPOSED: {WorkItemStatus.TRIAGED, WorkItemStatus.REJECTED},
    WorkItemStatus.TRIAGED: {
        WorkItemStatus.ACCEPTED,
        WorkItemStatus.REJECTED,
        WorkItemStatus.BLOCKED,
    },
    WorkItemStatus.ACCEPTED: {
        WorkItemStatus.IN_DESIGN,
        WorkItemStatus.REJECTED,
        WorkItemStatus.BLOCKED,
    },
    WorkItemStatus.IN_DESIGN: {
        WorkItemStatus.IMPLEMENTATION_IN_PROGRESS,
        WorkItemStatus.BLOCKED,
    },
    WorkItemStatus.IMPLEMENTATION_IN_PROGRESS: {
        WorkItemStatus.IMPLEMENTATION_COMPLETE,
        WorkItemStatus.BLOCKED,
    },
    WorkItemStatus.IMPLEMENTATION_COMPLETE: {
        WorkItemStatus.TESTING,
        WorkItemStatus.BLOCKED,
    },
    WorkItemStatus.TESTING: {
        WorkItemStatus.VERIFICATION_PENDING,
        WorkItemStatus.BLOCKED,
    },
    WorkItemStatus.VERIFICATION_PENDING: {
        WorkItemStatus.CERTIFICATION_PENDING,
        WorkItemStatus.BLOCKED,
    },
    WorkItemStatus.CERTIFICATION_PENDING: {
        WorkItemStatus.GOVERNANCE_PENDING,
        WorkItemStatus.BLOCKED,
    },
    WorkItemStatus.GOVERNANCE_PENDING: {
        WorkItemStatus.COMPLETED,
        WorkItemStatus.BLOCKED,
    },
    WorkItemStatus.BLOCKED: {
        WorkItemStatus.TRIAGED,
        WorkItemStatus.ACCEPTED,
        WorkItemStatus.IN_DESIGN,
        WorkItemStatus.IMPLEMENTATION_IN_PROGRESS,
        WorkItemStatus.REJECTED,
    },
    WorkItemStatus.COMPLETED: {WorkItemStatus.SUPERSEDED},
    WorkItemStatus.REJECTED: set(),
    WorkItemStatus.SUPERSEDED: set(),
}


def validate_transition(
    from_status: WorkItemStatus,
    to_status: WorkItemStatus,
) -> None:
    allowed = VALID_TRANSITIONS.get(from_status, set())
    if to_status not in allowed and to_status != WorkItemStatus.SUPERSEDED:
        raise InvalidStatusTransitionError(
            f"Cannot transition from {from_status.value} to {to_status.value}"
        )


def create_status_event(
    work_item_id: str,
    from_status: Optional[WorkItemStatus],
    to_status: WorkItemStatus,
    *,
    actor: str = "",
    rationale: str = "",
) -> StatusEvent:
    event_id = f"se_{uuid.uuid4().hex[:12]}"
    body = {
        "event_id": event_id,
        "work_item_id": work_item_id,
        "from_status": from_status.value if from_status else None,
        "to_status": to_status.value,
    }
    return StatusEvent(
        event_id=event_id,
        work_item_id=work_item_id,
        from_status=from_status,
        to_status=to_status,
        actor=actor,
        rationale=rationale,
        event_digest=digest_of(body),
    )


def validate_completion_gates(work_item) -> None:
    """Raise if work item cannot transition to completed."""
    _validate_completion_gates(work_item)
