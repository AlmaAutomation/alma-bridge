"""Certification platform errors."""

from __future__ import annotations


class CertificationError(Exception):
    """Base error for certification platform."""


class BehaviorNotFoundError(CertificationError):
    """Raised when a behavior certification target is not registered."""


class HistoryMutationError(CertificationError):
    """Raised when append-only certification history would be mutated."""
