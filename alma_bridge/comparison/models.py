"""Domain models for environment-aware session comparison."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from alma_bridge.knowledge.models import KnowledgeEvidenceReference


COMPARISON_SCHEMA_VERSION = "compatibility_session_comparison_v1"
COMPARISON_ENGINE_VERSION = "compatibility_session_comparison_diff_v1"

NON_CAUSALITY_NOTICE = (
    "Environment and verification outcome both changed between these sessions. "
    "Alma does not infer causality from this comparison."
)


class SessionComparisonValue(BaseModel):
    field: str
    before: Optional[str] = None
    after: Optional[str] = None
    changed: bool = False
    comparison_id: str
    evidence_references: List[KnowledgeEvidenceReference] = Field(default_factory=list)

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


class SessionEnvironmentComparison(BaseModel):
    baseline_session_id: str
    comparison_session_id: str
    application_fingerprint: str
    application_name: str
    environment_changes: List[SessionComparisonValue] = Field(default_factory=list)
    execution_changes: List[SessionComparisonValue] = Field(default_factory=list)
    verification_changes: List[SessionComparisonValue] = Field(default_factory=list)
    framework_changes: List[SessionComparisonValue] = Field(default_factory=list)
    runtime_changes: List[SessionComparisonValue] = Field(default_factory=list)
    unchanged_fields: List[str] = Field(default_factory=list)
    non_causality_notice: Optional[str] = None
    schema_version: str = COMPARISON_SCHEMA_VERSION
    engine_version: str = COMPARISON_ENGINE_VERSION
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @field_validator(
        "environment_changes",
        "execution_changes",
        "verification_changes",
        "framework_changes",
        "runtime_changes",
    )
    @classmethod
    def _sort_values(cls, value: List[SessionComparisonValue]) -> List[SessionComparisonValue]:
        return sorted(value, key=lambda item: (item.field, item.comparison_id))

    @field_validator("unchanged_fields")
    @classmethod
    def _sort_unchanged(cls, value: List[str]) -> List[str]:
        return sorted(value)


class ComparisonNotFoundError(Exception):
    """Raised when one or both sessions cannot be resolved."""


class ComparisonFingerprintMismatchError(Exception):
    """Raised when sessions belong to different applications."""


class MalformedComparisonEvidenceError(Exception):
    """Raised when session evidence cannot be compared safely."""

    def __init__(self, message: str, *, details: Optional[list[str]] = None) -> None:
        super().__init__(message)
        self.details = details or []
