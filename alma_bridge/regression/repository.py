"""Repository protocol for regression evidence reads."""

from __future__ import annotations

from alma_bridge.knowledge.repository import (
    KnowledgeEvidenceRepository,
    ReadOnlyKnowledgeEvidenceAdapter,
)

RegressionEvidenceRepository = KnowledgeEvidenceRepository

__all__ = [
    "RegressionEvidenceRepository",
    "ReadOnlyRegressionEvidenceAdapter",
]


class ReadOnlyRegressionEvidenceAdapter(ReadOnlyKnowledgeEvidenceAdapter):
    """Read-only adapter over persisted bridge session evidence."""
