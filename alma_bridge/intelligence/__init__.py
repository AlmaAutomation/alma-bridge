"""Read-only Compatibility Intelligence — deterministic evidence assessment."""

from alma_bridge.intelligence.models import (
    CompatibilityAssessment,
    CompatibilityFact,
    CompatibilityHypothesis,
    ConfidenceSummary,
    EvidenceBundle,
    EvidenceReference,
)
from alma_bridge.intelligence.service import CompatibilityIntelligenceService

__all__ = [
    "CompatibilityAssessment",
    "CompatibilityFact",
    "CompatibilityHypothesis",
    "ConfidenceSummary",
    "CompatibilityIntelligenceService",
    "EvidenceBundle",
    "EvidenceReference",
]
