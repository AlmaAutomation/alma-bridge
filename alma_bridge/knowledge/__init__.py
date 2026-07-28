"""Read-only Compatibility Knowledge — evidence-derived aggregation."""

from alma_bridge.knowledge.models import (
    CompatibilityKnowledgeProfile,
    KnowledgeEvidenceReference,
)
from alma_bridge.knowledge.service import CompatibilityKnowledgeService

__all__ = [
    "CompatibilityKnowledgeProfile",
    "CompatibilityKnowledgeService",
    "KnowledgeEvidenceReference",
]
