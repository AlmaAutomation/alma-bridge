"""Provenance normalization — bridge legacy models to canonical evidence.Provenance."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from alma_bridge.evidence.models import Provenance as CanonicalProvenance

if TYPE_CHECKING:
    from alma_bridge.compatibility_intelligence.models import ProvenanceEvidence
    from alma_bridge.decision.models import ProvenanceRef
    from alma_bridge.knowledge.models import KnowledgeEvidenceReference


def from_aci_provenance(ref: ProvenanceEvidence) -> CanonicalProvenance:
    return CanonicalProvenance(
        source=ref.source,
        artifact_id=ref.artifact_id,
        digest=ref.digest,
        detail=ref.detail,
    )


def from_decision_provenance(ref: ProvenanceRef) -> CanonicalProvenance:
    return CanonicalProvenance(
        source=ref.source,
        artifact_id=ref.artifact_id,
        digest=ref.digest,
        session_id=ref.session_id,
        attempt_id=ref.attempt_id,
        captured_at=ref.captured_at,
    )


def from_knowledge_reference(
    ref: KnowledgeEvidenceReference,
    *,
    source: Optional[str] = None,
) -> CanonicalProvenance:
    return CanonicalProvenance(
        source=source or ref.source_type,
        artifact_id=ref.source_id,
        digest=ref.artifact_key,
        session_id=ref.session_id,
        attempt_id=ref.attempt_id,
        captured_at=ref.captured_at,
        detail=ref.excerpt or "",
    )


def to_aci_provenance(ref: CanonicalProvenance) -> ProvenanceEvidence:
    from alma_bridge.compatibility_intelligence.models import ProvenanceEvidence

    return ProvenanceEvidence(
        source=ref.source,
        artifact_id=ref.artifact_id,
        digest=ref.digest,
        detail=ref.detail,
    )


def to_decision_provenance(ref: CanonicalProvenance) -> ProvenanceRef:
    from alma_bridge.decision.models import ProvenanceRef

    return ProvenanceRef(
        source=ref.source,
        artifact_id=ref.artifact_id,
        digest=ref.digest,
        session_id=ref.session_id,
        attempt_id=ref.attempt_id,
        captured_at=ref.captured_at,
    )
