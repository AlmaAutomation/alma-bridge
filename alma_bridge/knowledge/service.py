"""Compatibility Knowledge service facade — read-only evidence aggregation."""

from __future__ import annotations

from alma_bridge.intelligence.evidence import EvidenceBundleBuilder
from alma_bridge.intelligence.models import IntelligenceNotFoundError, MalformedEvidenceError
from alma_bridge.knowledge.aggregation import KnowledgeAggregationEngine
from alma_bridge.knowledge.models import (
    CompatibilityKnowledgeProfile,
    KnowledgeNotFoundError,
    MalformedKnowledgeEvidenceError,
)
from alma_bridge.knowledge.repository import (
    KnowledgeEvidenceRepository,
    ReadOnlyKnowledgeEvidenceAdapter,
)


class CompatibilityKnowledgeService:
    """Read-only knowledge profile queries backed by evidence aggregation only."""

    def __init__(
        self,
        repository: KnowledgeEvidenceRepository | None = None,
        engine: KnowledgeAggregationEngine | None = None,
    ) -> None:
        self._repository = repository or ReadOnlyKnowledgeEvidenceAdapter()
        self._builder = EvidenceBundleBuilder(self._repository)
        self._engine = engine or KnowledgeAggregationEngine()

    def profile_for_application(self, fingerprint: str) -> CompatibilityKnowledgeProfile:
        try:
            bundle = self._builder.for_application(fingerprint)
        except IntelligenceNotFoundError as exc:
            raise KnowledgeNotFoundError(str(exc)) from exc
        except MalformedEvidenceError as exc:
            raise MalformedKnowledgeEvidenceError(str(exc), details=exc.details) from exc
        try:
            return self._engine.aggregate(bundle)
        except MalformedKnowledgeEvidenceError:
            raise
