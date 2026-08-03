"""Canonical evidence models — shared vocabulary across Alma subsystems."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

EVIDENCE_SCHEMA_VERSION = "compatibility_evidence_v2"
EVIDENCE_ENGINE_VERSION = "compatibility_evidence_service_v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class TimelineEventType(str, Enum):
    ANALYSIS_CREATED = "AnalysisCreated"
    PREDICTION_GENERATED = "PredictionGenerated"
    EXECUTION_STARTED = "ExecutionStarted"
    VERIFICATION_COMPLETED = "VerificationCompleted"
    KNOWLEDGE_UPDATED = "KnowledgeUpdated"
    REGRESSION_DETECTED = "RegressionDetected"
    DECISION_GENERATED = "DecisionGenerated"
    REVIEW_APPROVED = "ReviewApproved"
    VALIDATION_COMPLETED = "ValidationCompleted"
    GOVERNANCE_APPLIED = "GovernanceApplied"
    EXPANSION_CANDIDATE_GENERATED = "ExpansionCandidateGenerated"


class Provenance(BaseModel):
    """Canonical provenance reference — normalized across subsystems."""

    source: str
    artifact_id: str
    digest: str = ""
    detail: str = ""
    session_id: Optional[str] = None
    attempt_id: Optional[int] = None
    captured_at: Optional[str] = None

    @field_validator("source", "artifact_id")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("provenance requires non-empty source and artifact_id")
        return value.strip()


class SectionReference(BaseModel):
    """Immutable reference to an existing artifact — no duplication."""

    section: str
    artifact_id: str
    digest: str
    provenance: Provenance
    schema_version: str = ""


class Capability(BaseModel):
    capability_id: str
    description: str = ""
    maturity_state: str = "unknown"
    provider_id: str = ""
    behavior_profile: List[str] = Field(default_factory=list)


class BehaviorProfile(BaseModel):
    profile_id: str
    behaviors: List[str] = Field(default_factory=list)
    maturity_state: str = "unknown"
    evidence_references: List[str] = Field(default_factory=list)


class CompatibilityEvidence(BaseModel):
    """Base compatibility evidence with provenance."""

    evidence_id: str
    digest: str
    provenance: Provenance
    schema_version: str = EVIDENCE_SCHEMA_VERSION


class VerificationEvidence(CompatibilityEvidence):
    session_id: str
    attempt_number: int = 0
    verified: bool = False
    verdict_summary: str = ""


class PredictionEvidence(CompatibilityEvidence):
    snapshot_id: str = ""
    native_compatible: bool = False
    wine_compatible: bool = False
    confidence_score: float = Field(ge=0.0, le=1.0, default=0.0)
    registry_version: str = ""


class CalibrationEvidence(CompatibilityEvidence):
    capability_id: str = ""
    sample_size: int = Field(ge=0, default=0)
    precision: float = Field(ge=0.0, le=1.0, default=0.0)
    recall: float = Field(ge=0.0, le=1.0, default=0.0)


class GovernanceEvidence(CompatibilityEvidence):
    registry_version: str = ""
    proposal_id: str = ""
    capability_id: str = ""
    maturity_state: str = ""


class ExpansionEvidence(CompatibilityEvidence):
    plan_id: str = ""
    candidate_count: int = Field(ge=0, default=0)
    backlog_size: int = Field(ge=0, default=0)


class DecisionEvidence(CompatibilityEvidence):
    plan_id: str = ""
    recommendation_count: int = Field(ge=0, default=0)
    review_id: str = ""
    validation_id: str = ""


class TimelineEvent(BaseModel):
    """Immutable lifecycle event — append-only."""

    event_id: str
    event_type: TimelineEventType
    timestamp: str
    version: int = Field(ge=1, default=1)
    evidence_digest: str
    schema_version: str = EVIDENCE_SCHEMA_VERSION
    source: str
    references: List[str] = Field(default_factory=list)
    provenance: Provenance
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BundleVersion(BaseModel):
    """Historical bundle version for replay."""

    version: int
    bundle_digest: str
    created_at: str
    event_count: int = Field(ge=0, default=0)
    registry_version: Optional[str] = None
    prediction_snapshot_id: Optional[str] = None


class CompatibilityEvidenceBundle(BaseModel):
    """Unified read model — one executable's complete compatibility story."""

    bundle_id: str
    binary_digest: str
    application_fingerprint: str = ""
    application_name: str = ""
    created_at: str
    updated_at: str
    bundle_digest: str
    schema_version: str = EVIDENCE_SCHEMA_VERSION
    engine_version: str = EVIDENCE_ENGINE_VERSION
    version: int = Field(ge=1, default=1)

    executable: SectionReference
    static_analysis: Optional[SectionReference] = None
    capability_graph: Optional[SectionReference] = None
    coverage: Optional[SectionReference] = None
    prediction: Optional[SectionReference] = None
    prediction_snapshot: Optional[SectionReference] = None
    execution: Optional[SectionReference] = None
    runtime_provider: Optional[SectionReference] = None
    verification: Optional[SectionReference] = None
    knowledge: Optional[SectionReference] = None
    regression: Optional[SectionReference] = None
    advisor: Optional[SectionReference] = None
    decision: Optional[SectionReference] = None
    review: Optional[SectionReference] = None
    validation: Optional[SectionReference] = None
    governance: Optional[SectionReference] = None
    expansion: Optional[SectionReference] = None
    historical_versions: List[BundleVersion] = Field(default_factory=list)

    limitations: List[str] = Field(default_factory=list)

    @field_validator("historical_versions")
    @classmethod
    def _sort_versions(cls, value: List[BundleVersion]) -> List[BundleVersion]:
        return sorted(value, key=lambda v: v.version)


class PlatformHealthMetric(BaseModel):
    name: str
    value: float
    sample_size: int = Field(ge=0, default=0)
    unit: str = ""
    evidence_source: str = ""


class PlatformHealthReport(BaseModel):
    generated_at: str
    schema_version: str = EVIDENCE_SCHEMA_VERSION
    metrics: List[PlatformHealthMetric] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
