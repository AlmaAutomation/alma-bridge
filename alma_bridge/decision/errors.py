"""Errors for the read-only Decision Engine."""

from __future__ import annotations

from typing import List, Optional


class DecisionNotFoundError(Exception):
    """Raised when no evidence exists for the requested decision query."""


class InsufficientEvidenceError(Exception):
    """Raised when evidence is too sparse to produce actionable recommendations."""

    def __init__(self, message: str, *, details: Optional[List[str]] = None) -> None:
        super().__init__(message)
        self.details = details or []


class MalformedDecisionEvidenceError(Exception):
    """Raised when upstream evidence cannot be evaluated safely."""

    def __init__(self, message: str, *, details: Optional[List[str]] = None) -> None:
        super().__init__(message)
        self.details = details or []
