"""Native engineering platform errors."""

from __future__ import annotations


class NativeEngineeringError(Exception):
    """Base error for native engineering platform."""


class SpecificationNotFoundError(NativeEngineeringError):
    """Raised when an API specification is not registered."""


class BenchmarkExecutionError(NativeEngineeringError):
    """Raised when a benchmark run fails."""


class HistoryMutationError(NativeEngineeringError):
    """Raised when append-only history would be mutated."""
