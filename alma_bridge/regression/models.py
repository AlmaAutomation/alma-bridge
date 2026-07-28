"""Domain models for Compatibility Regression Intelligence."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from alma_bridge.knowledge.models import KnowledgeEvidenceReference


REGRESSION_SCHEMA_VERSION = "compatibility_regression_v1"
REGRESSION_ENGINE_VERSION = "compatibility_regression_diff_v1"


class RegressionType(str, Enum):
    VERIFIED_SUCCESS_TO_VERIFIED_FAILURE = "verified_success_to_verified_failure"
    FRAMEWORK_CHANGED = "framework_changed"
    STRATEGY_SUCCESS_RATE_DROPPED = "strategy_success_rate_dropped"
    VERIFICATION_CONTRACT_CHANGED = "verification_contract_changed"
    RUNTIME_OBSERVATION_CHANGED = "runtime_observation_changed"
    NEW_CONFLICT = "new_conflict"


class RegressionSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"
    NOTICE = "notice"


_SEVERITY_BY_TYPE = {
    RegressionType.VERIFIED_SUCCESS_TO_VERIFIED_FAILURE: RegressionSeverity.CRITICAL,
    RegressionType.STRATEGY_SUCCESS_RATE_DROPPED: RegressionSeverity.WARNING,
    RegressionType.NEW_CONFLICT: RegressionSeverity.WARNING,
    RegressionType.FRAMEWORK_CHANGED: RegressionSeverity.INFO,
    RegressionType.VERIFICATION_CONTRACT_CHANGED: RegressionSeverity.INFO,
    RegressionType.RUNTIME_OBSERVATION_CHANGED: RegressionSeverity.INFO,
}


def severity_for_regression_type(regression_type: RegressionType) -> RegressionSeverity:
    return _SEVERITY_BY_TYPE.get(regression_type, RegressionSeverity.NOTICE)


class RegressionStateSnapshot(BaseModel):
    dimension: str
    label: str
    value: str
    evidence_references: List[KnowledgeEvidenceReference] = Field(default_factory=list)

    @field_validator("evidence_references")
    @classmethod
    def _require_provenance(
        cls,
        value: List[KnowledgeEvidenceReference],
    ) -> List[KnowledgeEvidenceReference]:
        if not value:
            raise ValueError("regression state snapshots require at least one evidence reference")
        return sorted(
            value,
            key=lambda ref: (ref.source_type, ref.source_id, ref.artifact_key),
        )


class RegressionFinding(BaseModel):
    regression_id: str
    application_fingerprint: str
    application_name: str
    regression_type: RegressionType
    severity: RegressionSeverity
    subject: str
    previous_state: RegressionStateSnapshot
    current_state: RegressionStateSnapshot
    first_observed_at: str
    comparison_session_id: str = ""
    baseline_session_ids: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    summary: str
    evidence_references: List[KnowledgeEvidenceReference] = Field(default_factory=list)

    @field_validator("baseline_session_ids")
    @classmethod
    def _sort_baseline_ids(cls, value: List[str]) -> List[str]:
        return sorted(value)

    @field_validator("evidence_references")
    @classmethod
    def _sort_evidence(
        cls,
        value: List[KnowledgeEvidenceReference],
    ) -> List[KnowledgeEvidenceReference]:
        return sorted(
            value,
            key=lambda ref: (ref.source_type, ref.source_id, ref.artifact_key),
        )


class CompatibilityRegressionReport(BaseModel):
    application_fingerprint: str
    application_name: str
    comparison_session_id: str
    baseline_session_count: int = Field(ge=0)
    current_session_count: int = Field(ge=0)
    regressions: List[RegressionFinding] = Field(default_factory=list)
    findings: List[RegressionFinding] = Field(default_factory=list)
    unchanged_summary: str = ""
    schema_version: str = REGRESSION_SCHEMA_VERSION
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @field_validator("regressions", "findings")
    @classmethod
    def _sort_findings(cls, value: List[RegressionFinding]) -> List[RegressionFinding]:
        return sorted(
            value,
            key=lambda item: (
                item.regression_type.value,
                item.subject,
                item.regression_id,
            ),
        )


class RegressionNotFoundError(Exception):
    """Raised when no evidence exists for the requested regression query."""


class InsufficientBaselineError(Exception):
    """Raised when comparison cannot proceed due to missing baseline sessions."""
