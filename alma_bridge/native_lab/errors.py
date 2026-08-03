"""Native Runtime Development Laboratory errors."""

from __future__ import annotations


class NativeLabError(Exception):
    """Base error for native lab operations."""


class WorkItemNotFoundError(NativeLabError):
    """Work item does not exist."""


class CandidateNotFoundError(NativeLabError):
    """Expansion candidate not found."""


class HistoryMutationError(NativeLabError):
    """Attempt to mutate append-only history."""


class InvalidStatusTransitionError(NativeLabError):
    """Status transition not allowed."""


class EvidenceGateError(NativeLabError):
    """Completion blocked by missing evidence gates."""


class DependencyCycleError(NativeLabError):
    """Dependency graph contains a cycle."""


class WaiverNotAllowedError(NativeLabError):
    """Critical criterion cannot be silently waived."""


class WorkItemAlreadyExistsError(NativeLabError):
    """Work item already exists for this scope."""
