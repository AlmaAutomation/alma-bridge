"""Errors for approved plan validation and dry-run."""

from __future__ import annotations

from typing import List, Optional


class DecisionValidationError(Exception):
    """Base error for decision validation operations."""


class DecisionValidationNotFoundError(DecisionValidationError):
    """Raised when a referenced review or plan cannot be resolved."""


class DecisionValidationModeError(DecisionValidationError):
    """Raised when an unsupported validation mode is requested."""


class DecisionValidationPolicyError(DecisionValidationError):
    """Raised when validation preconditions fail."""

    def __init__(self, message: str, *, violations: Optional[List[dict]] = None) -> None:
        super().__init__(message)
        self.violations = violations or []
