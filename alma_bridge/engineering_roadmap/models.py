"""Pydantic models for the Engineering Roadmap Generator (read-only, advisory)."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from alma_bridge.compatibility_intelligence.expansion.models import (
    ComplexityAssessment,
    EvidenceQualityLevel,
    SecurityRiskAssessment,
    SemanticRiskAssessment,
)
from alma_bridge.runtime_intelligence.models import BehaviorFamilyId, CorpusKind

ENGINEERING_ROADMAP_SCHEMA_VERSION = "engineering_roadmap_v1"
ENGINEERING_ROADMAP_FORMULA_VERSION = "engineering_roadmap_composition_v1"
ENGINEERING_ROADMAP_ENGINE_VERSION = "engineering_roadmap_service_v1"

PREDICTED_UNLOCK_DISCLAIMER_TEMPLATE = (
    "Potentially unlocks bounded eligibility for {count} application(s). "
    "Removing this blocker does not guarantee application compatibility."
)


class RoadmapOpportunityStatus(str, Enum):
    DESCRIPTIVE_ONLY = "descriptive_only"
    PRELIMINARY = "preliminary"
    RANKABLE = "rankable"
    BLOCKED_BY_PREREQUISITE = "blocked_by_prerequisite"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class EngineeringConfidenceLevel(str, Enum):
    VERY_HIGH = "very_high"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class BlockerClusterClassification(str, Enum):
    KNOWN = "known"
    PROVISIONAL = "provisional"
    UNKNOWN = "unknown"


class BlockerClusterSpec(BaseModel):
    """Registry-backed specification for a bounded blocker cluster."""

    model_config = {"frozen": True}

    cluster_id: str
    title: str
    api_symbols: List[str]
    capability_id: str
    behavior_id: Optional[str] = None
    family_id: BehaviorFamilyId
    prerequisite_capability_ids: List[str] = Field(default_factory=list)
    independently_implementable: bool = True
    registry_version: str
    limitations: List[str] = Field(default_factory=list)


class ProvisionalBlockerCluster(BaseModel):
    """Observed blocker symbols grouped into a bounded behavior cluster."""

    cluster_id: str
    title: str
    api_symbols: List[str]
    capability_id: str
    behavior_id: Optional[str] = None
    family_id: BehaviorFamilyId
    classification: BlockerClusterClassification
    prerequisite_capability_ids: List[str] = Field(default_factory=list)
    independently_implementable: bool = True
    fixture_available: bool = False
    native_alma_coverage_percent: Optional[float] = None
    evidence_quality: EvidenceQualityLevel = EvidenceQualityLevel.INSUFFICIENT
    suitable_as_bounded_opportunity: bool = False
    suitability_reason: str = ""
    limitations: List[str] = Field(default_factory=list)
    evidence_references: List[str] = Field(default_factory=list)
    digest: str


class UnclusteredBlocker(BaseModel):
    """Blocker that could not be assigned to a registry-backed cluster."""

    raw_blocker: str
    parsed_symbol: Optional[str] = None
    reason: str
    evidence_references: List[str] = Field(default_factory=list)
    digest: str


class BlockerClusteringResult(BaseModel):
    """Deterministic output of registry-backed blocker clustering."""

    clusters: List[ProvisionalBlockerCluster] = Field(default_factory=list)
    unclustered: List[UnclusteredBlocker] = Field(default_factory=list)
    input_blocker_count: int = Field(ge=0, default=0)
    clustered_blocker_count: int = Field(ge=0, default=0)
    unclustered_blocker_count: int = Field(ge=0, default=0)
    registry_version: str
    evidence_snapshot_digest: str
    report_digest: str


class EngineeringRoadmapOpportunity(BaseModel):
    """Evidence-backed engineering consideration — not approved or implemented."""

    opportunity_id: str
    corpus: CorpusKind
    provider_id: str
    family_id: BehaviorFamilyId
    capability_id: str
    behavior_id: Optional[str] = None
    bounded_scope: str
    title: str
    summary: str

    distinct_applications_blocked: int = Field(ge=0, default=0)
    distinct_binaries_blocked: int = Field(ge=0, default=0)
    application_classes_blocked: List[str] = Field(default_factory=list)
    blocked_session_count: int = Field(ge=0, default=0)
    application_mentions: int = Field(ge=0, default=0)

    predicted_applications_unlocked: int = Field(ge=0, default=0)
    predicted_application_classes_unlocked: int = Field(ge=0, default=0)
    predicted_unlock_disclaimer: str = Field(default=PREDICTED_UNLOCK_DISCLAIMER_TEMPLATE.format(count=0))

    engineering_complexity: ComplexityAssessment
    implementation_risk: float = Field(ge=0.0, le=1.0, default=0.0)
    security_risk: SecurityRiskAssessment
    semantic_risk: SemanticRiskAssessment
    maintenance_cost: Optional[str] = None
    fixture_availability: bool = False
    verification_readiness: str = "unknown"
    evidence_quality: EvidenceQualityLevel = EvidenceQualityLevel.INSUFFICIENT
    engineering_confidence: EngineeringConfidenceLevel = EngineeringConfidenceLevel.UNKNOWN
    engineering_confidence_factors: List[str] = Field(default_factory=list)

    existing_expansion_score: float = Field(ge=0.0, le=1.0, default=0.0)
    compatibility_impact_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    opportunity_status: RoadmapOpportunityStatus = RoadmapOpportunityStatus.INSUFFICIENT_EVIDENCE

    prerequisites: List[str] = Field(default_factory=list)
    prerequisite_opportunity_ids: List[str] = Field(default_factory=list)
    known_limitations: List[str] = Field(default_factory=list)

    affected_application_fingerprints: List[str] = Field(default_factory=list)
    affected_binary_digests: List[str] = Field(default_factory=list)
    source_debt_item_ids: List[str] = Field(default_factory=list)
    source_expansion_candidate_ids: List[str] = Field(default_factory=list)
    existing_work_item_ids: List[str] = Field(default_factory=list)
    certification_state: Optional[str] = None
    governance_state: Optional[str] = None
    evidence_references: List[str] = Field(default_factory=list)
    evidence_snapshot_digest: str
    registry_version: str
    provider_version: str
    schema_version: str = ENGINEERING_ROADMAP_SCHEMA_VERSION
    formula_version: str = ENGINEERING_ROADMAP_FORMULA_VERSION
    digest: str


class EngineeringRoadmapReport(BaseModel):
    """Corpus-scoped engineering roadmap summary — advisory only."""

    corpus: CorpusKind
    provider_id: str
    generated_at: str
    evidence_snapshot_digest: str
    opportunities: List[EngineeringRoadmapOpportunity] = Field(default_factory=list)
    blocked_application_count: int = Field(ge=0, default=0)
    explained_blocker_count: int = Field(ge=0, default=0)
    unexplained_blocker_count: int = Field(ge=0, default=0)
    limitations: List[str] = Field(default_factory=list)
    evidence_references: List[str] = Field(default_factory=list)
    schema_version: str = ENGINEERING_ROADMAP_SCHEMA_VERSION
    engine_version: str = ENGINEERING_ROADMAP_ENGINE_VERSION
    report_digest: str
