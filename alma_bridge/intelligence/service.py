"""Compatibility Intelligence service facade."""

from __future__ import annotations

from alma_bridge.intelligence.assessment import CompatibilityAssessmentEngine
from alma_bridge.intelligence.evidence import EvidenceBundleBuilder
from alma_bridge.intelligence.models import CompatibilityAssessment, EvidenceBundle
from alma_bridge.intelligence.repository import (
    CompatibilityEvidenceRepository,
    OutcomesStoreAdapter,
)


class CompatibilityIntelligenceService:
    """Read-only assessment entry point for sessions and application fingerprints."""

    def __init__(
        self,
        repository: CompatibilityEvidenceRepository | None = None,
        engine: CompatibilityAssessmentEngine | None = None,
    ) -> None:
        self._repository = repository or OutcomesStoreAdapter()
        self._builder = EvidenceBundleBuilder(self._repository)
        self._engine = engine or CompatibilityAssessmentEngine()

    def build_evidence_for_session(self, session_id: str) -> EvidenceBundle:
        return self._builder.for_session(session_id)

    def build_evidence_for_application(self, fingerprint: str) -> EvidenceBundle:
        return self._builder.for_application(fingerprint)

    def assess_session(self, session_id: str) -> CompatibilityAssessment:
        bundle = self.build_evidence_for_session(session_id)
        return self._engine.assess(bundle)

    def assess_application(self, fingerprint: str) -> CompatibilityAssessment:
        bundle = self.build_evidence_for_application(fingerprint)
        return self._engine.assess(bundle)
