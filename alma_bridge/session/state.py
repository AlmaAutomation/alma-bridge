from __future__ import annotations

from enum import Enum
from typing import FrozenSet, Mapping, Set


class SessionState(str, Enum):
    CREATED = "CREATED"
    INSPECTING = "INSPECTING"
    PLANNING = "PLANNING"
    POLICY_CHECK = "POLICY_CHECK"
    EXECUTING = "EXECUTING"
    OBSERVING = "OBSERVING"
    CLASSIFYING = "CLASSIFYING"
    REMEDIATING = "REMEDIATING"
    RETRYING = "RETRYING"
    VERIFYING = "VERIFYING"
    ESCALATING = "ESCALATING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_STATES: FrozenSet[SessionState] = frozenset({
    SessionState.SUCCEEDED,
    SessionState.FAILED,
    SessionState.CANCELLED,
})


ALLOWED_TRANSITIONS: Mapping[SessionState, FrozenSet[SessionState]] = {
    SessionState.CREATED: frozenset({
        SessionState.INSPECTING,
        SessionState.CANCELLED,
        SessionState.FAILED,
    }),
    SessionState.INSPECTING: frozenset({
        SessionState.PLANNING,
        SessionState.FAILED,
        SessionState.CANCELLED,
    }),
    SessionState.PLANNING: frozenset({
        SessionState.POLICY_CHECK,
        SessionState.FAILED,
        SessionState.CANCELLED,
    }),
    SessionState.POLICY_CHECK: frozenset({
        SessionState.EXECUTING,
        SessionState.REMEDIATING,
        SessionState.ESCALATING,
        SessionState.AWAITING_APPROVAL,
        SessionState.FAILED,
        SessionState.CANCELLED,
    }),
    SessionState.EXECUTING: frozenset({
        SessionState.OBSERVING,
        SessionState.FAILED,
        SessionState.CANCELLED,
    }),
    SessionState.OBSERVING: frozenset({
        SessionState.CLASSIFYING,
        SessionState.VERIFYING,
        SessionState.CANCELLED,
        SessionState.FAILED,
    }),
    SessionState.CLASSIFYING: frozenset({
        SessionState.VERIFYING,
        SessionState.REMEDIATING,
        SessionState.RETRYING,
        SessionState.ESCALATING,
        SessionState.FAILED,
        SessionState.CANCELLED,
    }),
    SessionState.REMEDIATING: frozenset({
        SessionState.POLICY_CHECK,
        SessionState.EXECUTING,
        SessionState.FAILED,
        SessionState.CANCELLED,
    }),
    SessionState.RETRYING: frozenset({
        SessionState.POLICY_CHECK,
        SessionState.PLANNING,
        SessionState.FAILED,
        SessionState.CANCELLED,
    }),
    SessionState.VERIFYING: frozenset({
        SessionState.SUCCEEDED,
        SessionState.CLASSIFYING,
        SessionState.REMEDIATING,
        SessionState.RETRYING,
        SessionState.ESCALATING,
        SessionState.FAILED,
        SessionState.CANCELLED,
    }),
    SessionState.ESCALATING: frozenset({
        SessionState.POLICY_CHECK,
        SessionState.EXECUTING,
        SessionState.VERIFYING,
        SessionState.AWAITING_APPROVAL,
        SessionState.FAILED,
        SessionState.CANCELLED,
    }),
    SessionState.AWAITING_APPROVAL: frozenset({
        SessionState.POLICY_CHECK,
        SessionState.ESCALATING,
        SessionState.FAILED,
        SessionState.CANCELLED,
    }),
    SessionState.SUCCEEDED: frozenset(),
    SessionState.FAILED: frozenset(),
    SessionState.CANCELLED: frozenset(),
}


def is_terminal(state: SessionState) -> bool:
    return state in TERMINAL_STATES


def validate_transition(current: SessionState, target: SessionState) -> None:
    allowed: Set[SessionState] = set(ALLOWED_TRANSITIONS.get(current, frozenset()))
    if target not in allowed:
        raise ValueError(
            f"Illegal session transition {current.value} -> {target.value}; "
            f"allowed={sorted(s.value for s in allowed)}"
        )
