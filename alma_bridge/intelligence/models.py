"""Domain models for Compatibility Intelligence assessments."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


INTELLIGENCE_SCHEMA_VERSION = "compatibility_intelligence_v1"


class EvidenceSourceType(str, Enum):
    SESSION = "session"
    ATTEMPT = "attempt"
    VERIFICATION = "verification"
    FRAMEWORK_DETECTION = "framework_detection"
    MANIFEST_CAPTURE = "manifest_capture"
    SHADOW_COMPARISON = "shadow_comparison"
    INSPECTION = "inspection"


VALID_EVIDENCE_SOURCE_TYPES = frozenset(item.value for item in EvidenceSourceType)


class EvidenceReference(BaseModel):
    schema_version: str = INTELLIGENCE_SCHEMA_VERSION
    source_type: EvidenceSourceType
    source_id: str
    artifact_key: str = ""
    captured_at: Optional[str] = None
    excerpt: Optional[str] = None

    @field_validator("source_type", mode="before")
    @classmethod
    def _validate_source_type(cls, value: object) -> object:
        if isinstance(value, str) and value not in VALID_EVIDENCE_SOURCE_TYPES:
            raise ValueError(f"invalid evidence source_type: {value}")
        return value


class FactKind(str, Enum):
    VERIFIED_SUCCESSFUL_LAUNCH = "verified_successful_launch"
    USES_FRAMEWORK = "uses_framework"
    VERIFIED_WITH_STRATEGY = "verified_with_strategy"
    CONFLICTING_EVIDENCE = "conflicting_evidence"


class FactStatus(str, Enum):
    PROVEN = "proven"
    OBSERVED = "observed"


class CompatibilityFact(BaseModel):
    schema_version: str = INTELLIGENCE_SCHEMA_VERSION
    fact_id: str
    kind: FactKind
    status: FactStatus
    statement: str
    provenance: List[EvidenceReference] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    attributes: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("provenance")
    @classmethod
    def _require_provenance(cls, value: List[EvidenceReference]) -> List[EvidenceReference]:
        if not value:
            raise ValueError("facts require at least one evidence reference")
        return sorted(value, key=lambda ref: (ref.source_type.value, ref.source_id, ref.artifact_key))


class HypothesisStatus(str, Enum):
    OPEN = "open"
    SUPPORTED = "supported"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"


class CompatibilityHypothesis(BaseModel):
    schema_version: str = INTELLIGENCE_SCHEMA_VERSION
    hypothesis_id: str
    question: str
    status: HypothesisStatus = HypothesisStatus.OPEN
    supporting_evidence: List[EvidenceReference] = Field(default_factory=list)
    contradicting_evidence: List[EvidenceReference] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class EvidenceBundle(BaseModel):
    schema_version: str = INTELLIGENCE_SCHEMA_VERSION
    session_id: Optional[str] = None
    application_fingerprint: Optional[str] = None
    file_path: Optional[str] = None
    references: List[EvidenceReference] = Field(default_factory=list)
    artifacts: Dict[str, Any] = Field(default_factory=dict)
    limitations: List[str] = Field(default_factory=list)

    @field_validator("references")
    @classmethod
    def _sort_references(cls, value: List[EvidenceReference]) -> List[EvidenceReference]:
        return sorted(value, key=lambda ref: (ref.source_type.value, ref.source_id, ref.artifact_key))


class ConfidenceSummary(BaseModel):
    schema_version: str = INTELLIGENCE_SCHEMA_VERSION
    overall: float = Field(ge=0.0, le=1.0, default=0.0)
    fact_count: int = 0
    hypothesis_count: int = 0
    open_questions: int = 0
    weights_applied: Dict[str, float] = Field(default_factory=dict)


class CompatibilityAssessment(BaseModel):
    schema_version: str = INTELLIGENCE_SCHEMA_VERSION
    engine_version: str = "compatibility_intelligence_v1"
    session_id: Optional[str] = None
    application_fingerprint: Optional[str] = None
    facts: List[CompatibilityFact] = Field(default_factory=list)
    hypotheses: List[CompatibilityHypothesis] = Field(default_factory=list)
    confidence: ConfidenceSummary = Field(default_factory=ConfidenceSummary)
    limitations: List[str] = Field(default_factory=list)
    assessed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @field_validator("facts")
    @classmethod
    def _sort_facts(cls, value: List[CompatibilityFact]) -> List[CompatibilityFact]:
        return sorted(value, key=lambda fact: (fact.kind.value, fact.fact_id))

    @field_validator("hypotheses")
    @classmethod
    def _sort_hypotheses(cls, value: List[CompatibilityHypothesis]) -> List[CompatibilityHypothesis]:
        return sorted(value, key=lambda item: item.hypothesis_id)


class IntelligenceNotFoundError(Exception):
    """Raised when no evidence exists for the requested scope."""


class MalformedEvidenceError(Exception):
    """Raised when persisted evidence cannot be interpreted safely."""

    def __init__(self, message: str, *, details: Optional[List[str]] = None) -> None:
        super().__init__(message)
        self.details = details or []
