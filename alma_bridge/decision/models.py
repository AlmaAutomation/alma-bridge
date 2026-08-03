"""Domain models for the read-only Decision Engine."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from alma_bridge.knowledge.models import KnowledgeEvidenceReference


DECISION_SCHEMA_VERSION = "compatibility_decision_v1"
DECISION_ENGINE_VERSION = "compatibility_decision_deterministic_v1"

VALID_RECOMMENDATION_KINDS = frozenset(
    {
        "strategy",
        "environment",
        "remediation_review",
        "verification_review",
        "hold",
        "evidence_review",
    }
)


class RecommendationKind(str, Enum):
    STRATEGY = "strategy"
    ENVIRONMENT = "environment"
    REMEDIATION_REVIEW = "remediation_review"
    VERIFICATION_REVIEW = "verification_review"
    HOLD = "hold"
    EVIDENCE_REVIEW = "evidence_review"


class ConfidenceLevel(BaseModel):
    level: str
    score: float = Field(ge=0.0, le=1.0)
    factors: List[str] = Field(default_factory=list)

    @field_validator("level")
    @classmethod
    def _normalize_level(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in {"high", "medium", "low"}:
            raise ValueError("confidence level must be high, medium, or low")
        return normalized

    @field_validator("factors")
    @classmethod
    def _sort_factors(cls, value: List[str]) -> List[str]:
        return sorted(value)


class Constraint(BaseModel):
    code: str
    description: str

    @field_validator("code", "description")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("constraint fields require non-empty values")
        return value.strip()


class ProvenanceRef(BaseModel):
    source: str
    artifact_id: str
    digest: str = ""
    session_id: Optional[str] = None
    attempt_id: Optional[int] = None
    captured_at: Optional[str] = None

    @field_validator("source", "artifact_id")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("provenance requires source and artifact_id")
        return value

    @classmethod
    def from_knowledge_reference(cls, ref: KnowledgeEvidenceReference, *, source: str) -> ProvenanceRef:
        return cls(
            source=source,
            artifact_id=ref.source_id,
            digest=ref.artifact_key,
            session_id=ref.session_id,
            attempt_id=ref.attempt_id,
            captured_at=ref.captured_at,
        )


class HumanApprovalRequirement(BaseModel):
    required: bool = True
    reasons: List[str] = Field(default_factory=list)

    @field_validator("reasons")
    @classmethod
    def _sort_reasons(cls, value: List[str]) -> List[str]:
        return sorted(value)

    @model_validator(mode="after")
    def _require_reasons_when_required(self) -> HumanApprovalRequirement:
        if self.required and not self.reasons:
            raise ValueError("human approval requires at least one reason when required=True")
        return self


class DecisionRecommendation(BaseModel):
    recommendation_id: str
    kind: RecommendationKind
    action: str
    confidence: ConfidenceLevel
    constraints: List[Constraint] = Field(default_factory=list)
    provenance: List[ProvenanceRef] = Field(default_factory=list)
    human_approval_required: bool = True
    approval_reasons: List[str] = Field(default_factory=list)

    @field_validator("constraints")
    @classmethod
    def _sort_constraints(cls, value: List[Constraint]) -> List[Constraint]:
        return sorted(value, key=lambda item: (item.code, item.description))

    @field_validator("provenance")
    @classmethod
    def _require_provenance(cls, value: List[ProvenanceRef]) -> List[ProvenanceRef]:
        if not value:
            raise ValueError("decision recommendations require at least one provenance reference")
        return sorted(
            value,
            key=lambda ref: (ref.source, ref.artifact_id, ref.digest),
        )

    @field_validator("approval_reasons")
    @classmethod
    def _sort_approval_reasons(cls, value: List[str]) -> List[str]:
        return sorted(value)

    @model_validator(mode="after")
    def _approval_invariants(self) -> DecisionRecommendation:
        if self.human_approval_required and not self.approval_reasons:
            raise ValueError("recommendations with human_approval_required need approval_reasons")
        return self


class DecisionInput(BaseModel):
    session_id: Optional[str] = None
    application_fingerprint: Optional[str] = None
    baseline_session_id: Optional[str] = None
    comparison_session_id: Optional[str] = None
    ask_question: Optional[str] = None

    @model_validator(mode="after")
    def _require_target(self) -> DecisionInput:
        if not self.session_id and not self.application_fingerprint:
            raise ValueError("session_id or application_fingerprint is required")
        return self


class EvidenceSummary(BaseModel):
    total_sessions: int = Field(ge=0, default=0)
    verified_successes: int = Field(ge=0, default=0)
    verified_failures: int = Field(ge=0, default=0)
    unverifiable_sessions: int = Field(ge=0, default=0)
    regression_finding_count: int = Field(ge=0, default=0)
    advisor_observation_count: int = Field(ge=0, default=0)
    comparison_included: bool = False
    ask_context_included: bool = False


class DecisionPlan(BaseModel):
    plan_id: str
    session_id: Optional[str] = None
    application_fingerprint: str
    application_name: str
    generated_at: str
    recommendations: List[DecisionRecommendation] = Field(default_factory=list)
    evidence_summary: EvidenceSummary
    notices: List[str] = Field(default_factory=list)
    schema_version: str = DECISION_SCHEMA_VERSION
    engine_version: str = DECISION_ENGINE_VERSION

    @field_validator("recommendations")
    @classmethod
    def _sort_recommendations(
        cls,
        value: List[DecisionRecommendation],
    ) -> List[DecisionRecommendation]:
        return sorted(value, key=lambda item: (item.kind.value, item.recommendation_id))

    @field_validator("notices")
    @classmethod
    def _sort_notices(cls, value: List[str]) -> List[str]:
        return sorted(set(value))
