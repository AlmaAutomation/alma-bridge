"""Runtime expansion planning errors."""

from __future__ import annotations


class ExpansionError(Exception):
    """Base error for expansion planning."""


class CandidateNotFoundError(ExpansionError):
    """Requested expansion candidate does not exist."""


class PlanGenerationError(ExpansionError):
    """Plan could not be generated from available evidence."""
