"""Pydantic models for runtime expansion planning."""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

ACI_EXPANSION_SCHEMA_VERSION = "compatibility_intelligence_expansion_v1"
EXPANSION_ENGINE_VERSION = "aci_expansion_v1"


class EngineeringComplexityLevel(str, Enum):
    TRIVIAL = "trivial"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"
    UNKNOWN = "unknown"


class SecurityRiskCategory(str, Enum):
    FILESYSTEM_ESCAPE = "filesystem_escape"
    ARBITRARY_PROCESS_CREATION = "arbitrary_process_creation"
    NETWORKING = "networking"
    REGISTRY_PERSISTENCE = "registry_persistence"
    MEMORY_PROTECTION = "memory_protection"
    CODE_LOADING = "code_loading"
    PRIVILEGE_BOUNDARY = "privilege_boundary"
    SYNCHRONIZATION_DEADLOCK = "synchronization_deadlock"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    PARSER_ATTACK_SURFACE = "parser_attack_surface"


class SemanticRiskCategory(str, Enum):
    BROAD_BEHAVIOR_SURFACE = "broad_behavior_surface"
    UNMODELED_FLAGS_OR_MODES = "unmodeled_flags_or_modes"
    ASYNC_CALLBACKS = "async_callbacks"
    UNDOCUMENTED_BEHAVIOR = "undocumented_behavior"
    CROSS_PROCESS_STATE = "cross_process_state"
    VERSION_SPECIFIC_BEHAVIOR = "version_specific_behavior"


class TestabilityLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class EvidenceQualityLevel(str, Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    INSUFFICIENT = "insufficient"


class DemandCounts(BaseModel):
    """Raw observed demand — sessions deduplicated by binary digest."""

    distinct_binary_digests: int = 0
    distinct_application_fingerprints: int = 0
    blocked_session_count: int = 0
    false_positive_gap_count: int = 0
    verified_wine_session_count: int = 0
    most_recent_evidence_at: Optional[str] = None


class BoundedImpactEstimate(BaseModel):
    """Estimated bounded impact — not a compatibility guarantee."""

    analyses_blocker_removable: int = 0
    binaries_ineligible_to_eligible: int = 0
    behavior_coverage_increase_percent: float = 0.0
    calibration_gaps_potentially_resolved: int = 0
    impact_summary: str = ""


class ComplexityAssessment(BaseModel):
    level: EngineeringComplexityLevel
    score: float = Field(ge=0.0, le=1.0)
    factors: List[str] = Field(default_factory=list)


class SecurityRiskAssessment(BaseModel):
    categories: List[SecurityRiskCategory] = Field(default_factory=list)
    score: float = Field(ge=0.0, le=1.0, default=0.0)
    explanations: Dict[str, str] = Field(default_factory=dict)


class SemanticRiskAssessment(BaseModel):
    categories: List[SemanticRiskCategory] = Field(default_factory=list)
    score: float = Field(ge=0.0, le=1.0, default=0.0)
    explanations: Dict[str, str] = Field(default_factory=dict)


class PriorityDimensions(BaseModel):
    """All ranking dimensions preserved — composite is advisory only."""

    demand_score: float = Field(ge=0.0, le=1.0)
    bounded_impact_score: float = Field(ge=0.0, le=1.0)
    engineering_cost_score: float = Field(ge=0.0, le=1.0)
    security_risk_score: float = Field(ge=0.0, le=1.0)
    semantic_risk_score: float = Field(ge=0.0, le=1.0)
    evidence_quality_score: float = Field(ge=0.0, le=1.0)
    testability_score: float = Field(ge=0.0, le=1.0)
    composite_score: float = Field(ge=0.0, le=1.0)


class RuntimeExpansionCandidate(BaseModel):
    """Bounded engineering candidate — not approved or implemented."""

    candidate_id: str
    provider_id: str
    capability_id: str
    behavior_id: Optional[str] = None
    dll_symbols: List[str] = Field(default_factory=list)
    implementation_scope: str
    architecture: str = "x64"
    subsystem: str = "console"
    affected_application_fingerprints: List[str] = Field(default_factory=list)
    affected_analysis_digests: List[str] = Field(default_factory=list)
    observed_demand_count: int = 0
    verified_session_count: int = 0
    blocked_session_count: int = 0
    false_positive_gap_count: int = 0
    demand: DemandCounts
    demand_score: float = Field(ge=0.0, le=1.0, default=0.0)
    estimated_coverage_gain: float = 0.0
    impact: BoundedImpactEstimate
    bounded_impact_score: float = Field(ge=0.0, le=1.0, default=0.0)
    prerequisite_capabilities: List[str] = Field(default_factory=list)
    engineering_complexity: ComplexityAssessment
    security_risk: SecurityRiskAssessment
    semantic_risk: SemanticRiskAssessment
    testability: TestabilityLevel = TestabilityLevel.MEDIUM
    testability_score: float = Field(ge=0.0, le=1.0, default=0.5)
    evidence_quality: EvidenceQualityLevel = EvidenceQualityLevel.MODERATE
    evidence_quality_score: float = Field(ge=0.0, le=1.0, default=0.5)
    priority: PriorityDimensions
    limitations: List[str] = Field(default_factory=list)
    evidence_references: List[str] = Field(default_factory=list)
    schema_version: str = ACI_EXPANSION_SCHEMA_VERSION


class ExcludedCandidate(BaseModel):
    candidate_id: str
    provider_id: str
    capability_id: str
    behavior_id: Optional[str] = None
    exclusion_reason: str


class RuntimeExpansionPlan(BaseModel):
    """Advisory expansion plan — no candidate marked approved/implemented."""

    plan_id: str
    registry_version: str
    analysis_window: Dict[str, str]
    ranked_candidates: List[RuntimeExpansionCandidate] = Field(default_factory=list)
    excluded_candidates: List[ExcludedCandidate] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    generated_at: str
    engine_version: str = EXPANSION_ENGINE_VERSION
    schema_version: str = ACI_EXPANSION_SCHEMA_VERSION
    evidence_digest: str
