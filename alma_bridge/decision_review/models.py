"""Domain models for decision plan review, approval, and export."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from alma_bridge.decision.models import ConfidenceLevel, Constraint, DecisionPlan, EvidenceSummary
from alma_bridge.knowledge.models import KnowledgeEvidenceReference


DECISION_REVIEW_SCHEMA_VERSION = "compatibility_decision_review_v1"
EXPORT_DISCLAIMER = "This artifact does not authorize or perform execution."
EXECUTION_STATUS_NOT_EXECUTED = "not_executed"
APPROVAL_TTL_DAYS = 30


class Decision(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"
    EXPIRED = "expired"


class PlanRisk(BaseModel):
    risk_id: str
    summary: str
    source: str
    severity: str = "warning"

    @field_validator("summary")
    @classmethod
    def _require_summary(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("risk summary is required")
        return value.strip()


class CandidateStep(BaseModel):
    step_id: str
    kind: str
    action: str
    confidence: ConfidenceLevel


class DecisionPlanSummary(BaseModel):
    plan_id: str
    plan_version: str
    plan_digest: str
    session_id: Optional[str] = None
    application_fingerprint: str
    application_name: str
    objective: str
    confidence: ConfidenceLevel
    evidence_summary: EvidenceSummary
    candidate_steps: List[CandidateStep] = Field(default_factory=list)
    constraints: List[Constraint] = Field(default_factory=list)
    risks: List[PlanRisk] = Field(default_factory=list)
    execution_status: str = EXECUTION_STATUS_NOT_EXECUTED
    latest_decision: Optional[Decision] = None
    approval_stale: bool = False
    review_required: bool = True
    schema_version: str = DECISION_REVIEW_SCHEMA_VERSION


class DecisionPlanReview(BaseModel):
    review_id: str
    plan_id: str
    application_fingerprint: str
    session_id: Optional[str] = None
    plan_version: str
    plan_digest: str
    decision: Decision
    reviewer: str
    reviewed_at: str
    comment: str = ""
    risk_acknowledgements: List[str] = Field(default_factory=list)
    evidence_references: List[KnowledgeEvidenceReference] = Field(default_factory=list)
    schema_version: str = DECISION_REVIEW_SCHEMA_VERSION

    @field_validator("reviewer")
    @classmethod
    def _require_reviewer(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("reviewer is required")
        return value.strip()

    @field_validator("risk_acknowledgements")
    @classmethod
    def _sort_risk_acknowledgements(cls, value: List[str]) -> List[str]:
        return sorted(set(value))


class DecisionPlanReviewRequest(BaseModel):
    decision: Decision
    reviewer: str
    comment: str = ""
    risk_acknowledgements: List[str] = Field(default_factory=list)
    plan_digest: str

    @field_validator("reviewer")
    @classmethod
    def _require_reviewer(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("reviewer is required")
        return value.strip()

    @field_validator("plan_digest")
    @classmethod
    def _require_digest(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("plan_digest is required")
        return value.strip()

    @model_validator(mode="after")
    def _decision_not_pending_or_expired(self) -> DecisionPlanReviewRequest:
        if self.decision in {Decision.PENDING, Decision.EXPIRED}:
            raise ValueError("decision must be approved, rejected, or needs_revision")
        return self


class DecisionPlanDetail(BaseModel):
    plan: DecisionPlan
    plan_version: str
    plan_digest: str
    summary: DecisionPlanSummary
    execution_status: str = EXECUTION_STATUS_NOT_EXECUTED


class DecisionPlanArtifact(BaseModel):
    artifact_id: str
    plan_id: str
    plan_version: str
    plan_digest: str
    format: str
    content: str
    exported_at: str
    disclaimer: str = EXPORT_DISCLAIMER
    execution_status: str = EXECUTION_STATUS_NOT_EXECUTED
    schema_version: str = DECISION_REVIEW_SCHEMA_VERSION


class PolicyViolation(BaseModel):
    code: str
    message: str


class PolicyValidationResult(BaseModel):
    allowed: bool
    violations: List[PolicyViolation] = Field(default_factory=list)


class ExportRequest(BaseModel):
    format: str = "json"
    plan_digest: str

    @field_validator("format")
    @classmethod
    def _normalize_format(cls, value: str) -> str:
        normalized = (value or "json").strip().lower()
        if normalized not in {"json", "markdown"}:
            raise ValueError("format must be json or markdown")
        return normalized

    @field_validator("plan_digest")
    @classmethod
    def _require_digest(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("plan_digest is required")
        return value.strip()
