"""Domain models for approved plan validation and dry-run reports."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from alma_bridge.knowledge.models import KnowledgeEvidenceReference


DECISION_VALIDATION_SCHEMA_VERSION = "compatibility_decision_validation_v1"
DRY_RUN_DISCLAIMER = (
    "No application was launched and no system state was changed. "
    "This dry-run report is observational only and does not authorize execution."
)


class PlanValidationStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    STALE = "stale"
    BLOCKED = "blocked"
    INDETERMINATE = "indeterminate"


class ValidationCheckSeverity(str, Enum):
    BLOCKING = "blocking"
    WARNING = "warning"
    INFO = "info"


class ValidationCheckCategory(str, Enum):
    PLAN_INTEGRITY = "plan_integrity"
    APPLICATION_IDENTITY = "application_identity"
    RUNTIME_FEASIBILITY = "runtime_feasibility"
    ENVIRONMENT_FEASIBILITY = "environment_feasibility"
    POLICY_FEASIBILITY = "policy_feasibility"
    VERIFICATION_READINESS = "verification_readiness"
    EVIDENCE_FRESHNESS = "evidence_freshness"


class ValidationCheck(BaseModel):
    check_id: str
    category: ValidationCheckCategory
    code: str
    message: str
    severity: ValidationCheckSeverity
    passed: bool
    evidence_refs: List[KnowledgeEvidenceReference] = Field(default_factory=list)

    @field_validator("code", "message")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("check code and message are required")
        return value.strip()


class ValidationRequest(BaseModel):
    plan_digest: str
    review_id: str
    session_id: Optional[str] = None
    mode: str = "dry_run"

    @field_validator("plan_digest", "review_id")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("plan_digest and review_id are required")
        return value.strip()

    @field_validator("mode")
    @classmethod
    def _normalize_mode(cls, value: str) -> str:
        normalized = (value or "dry_run").strip().lower()
        if normalized != "dry_run":
            raise ValueError("mode must be dry_run")
        return normalized


class DecisionPlanDryRunReport(BaseModel):
    validation_id: str
    plan_id: str
    plan_version: str
    plan_digest: str
    review_id: str
    session_id: Optional[str] = None
    application_fingerprint: str
    status: PlanValidationStatus
    approval_stale: bool = False
    checks: List[ValidationCheck] = Field(default_factory=list)
    validated_at: str
    mode: str = "dry_run"
    execution_performed: bool = False
    mutations_performed: bool = False
    disclaimer: str = DRY_RUN_DISCLAIMER
    evidence_references: List[KnowledgeEvidenceReference] = Field(default_factory=list)
    schema_version: str = DECISION_VALIDATION_SCHEMA_VERSION

    @model_validator(mode="after")
    def _non_executing_invariants(self) -> DecisionPlanDryRunReport:
        if self.execution_performed or self.mutations_performed:
            raise ValueError("dry-run reports must not perform execution or mutations")
        if self.mode != "dry_run":
            raise ValueError("validation mode must be dry_run")
        return self
