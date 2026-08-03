"""Errors for decision plan review."""

from __future__ import annotations

from typing import List, Optional


class DecisionReviewError(Exception):
    """Base error for decision review operations."""


class DecisionPlanMismatchError(DecisionReviewError):
    """Raised when plan_id does not match the rebuilt plan."""


class DecisionReviewPolicyError(DecisionReviewError):
    """Raised when approval policy validation fails."""

    def __init__(self, message: str, *, violations: Optional[List[dict]] = None) -> None:
        super().__init__(message)
        self.violations = violations or []
