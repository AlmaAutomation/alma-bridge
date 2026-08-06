"""Errors for the Engineering Roadmap Generator (read-only composition layer)."""


class EngineeringRoadmapError(Exception):
    """Base error for engineering roadmap operations."""


class InsufficientEvidenceError(EngineeringRoadmapError):
    """Raised when corpus or enrollment evidence is insufficient for the requested view."""


class OpportunityNotFoundError(EngineeringRoadmapError):
    """Raised when a roadmap opportunity identifier cannot be resolved."""
