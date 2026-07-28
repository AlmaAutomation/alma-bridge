"""Domain models for the read-only Compatibility Advisor."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from alma_bridge.knowledge.models import (
    CompatibilityKnowledgeProfile,
    KnowledgeEvidenceReference,
)
from alma_bridge.regression.models import CompatibilityRegressionReport


ADVISOR_SCHEMA_VERSION = "compatibility_advisor_v1"
ADVISOR_ENGINE_VERSION = "compatibility_advisor_deterministic_v1"

VALID_OBSERVATION_CATEGORIES = frozenset(
    {
        "verified_outcome_history",
        "framework_observation",
        "strategy_history",
        "runtime_observation",
        "verification_contract",
        "compatibility_change",
        "conflicting_evidence",
        "insufficient_evidence",
    }
)


class ObservationCategory(str, Enum):
    VERIFIED_OUTCOME_HISTORY = "verified_outcome_history"
    FRAMEWORK_OBSERVATION = "framework_observation"
    STRATEGY_HISTORY = "strategy_history"
    RUNTIME_OBSERVATION = "runtime_observation"
    VERIFICATION_CONTRACT = "verification_contract"
    COMPATIBILITY_CHANGE = "compatibility_change"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class SourceLayer(str, Enum):
    GRAPH = "graph"
    KNOWLEDGE = "knowledge"
    REGRESSION = "regression"


class GraphSummary(BaseModel):
    """Normalized graph-oriented summary derived from composed layer outputs."""

    application_fingerprint: str
    total_sessions: int = Field(ge=0)
    frameworks_observed: List[str] = Field(default_factory=list)
    strategies_observed: List[str] = Field(default_factory=list)
    runtimes_observed: List[str] = Field(default_factory=list)
    conflict_count: int = Field(ge=0, default=0)
    derived_from: str = "knowledge_profile"


class AdvisorContext(BaseModel):
    application_fingerprint: str
    application_name: str
    graph_summary: GraphSummary
    knowledge_profile: CompatibilityKnowledgeProfile
    regression_report: CompatibilityRegressionReport
    selected_session_id: Optional[str] = None
    evidence_references: List[KnowledgeEvidenceReference] = Field(default_factory=list)
    schema_version: str = ADVISOR_SCHEMA_VERSION

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


class AdvisorObservation(BaseModel):
    observation_id: str
    category: ObservationCategory
    title: str
    statement: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    severity: str = "info"
    evidence_references: List[KnowledgeEvidenceReference] = Field(default_factory=list)
    source_layer: SourceLayer

    @field_validator("evidence_references")
    @classmethod
    def _require_provenance(
        cls,
        value: List[KnowledgeEvidenceReference],
    ) -> List[KnowledgeEvidenceReference]:
        if not value:
            raise ValueError("advisor observations require at least one evidence reference")
        return sorted(
            value,
            key=lambda ref: (ref.source_type, ref.source_id, ref.artifact_key),
        )


class AdvisorExplanation(BaseModel):
    application_fingerprint: str
    application_name: str
    observations: List[AdvisorObservation] = Field(default_factory=list)
    summary: str
    limitations: List[str] = Field(default_factory=list)
    schema_version: str = ADVISOR_SCHEMA_VERSION
    engine_version: str = ADVISOR_ENGINE_VERSION
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @field_validator("observations")
    @classmethod
    def _sort_observations(cls, value: List[AdvisorObservation]) -> List[AdvisorObservation]:
        return sorted(
            value,
            key=lambda item: (item.category.value, item.observation_id),
        )

    @field_validator("limitations")
    @classmethod
    def _sort_limitations(cls, value: List[str]) -> List[str]:
        return sorted(value)


class AdvisorNotFoundError(Exception):
    """Raised when no evidence exists for the requested advisor query."""


class MalformedAdvisorError(Exception):
    """Raised when upstream evidence cannot be explained safely."""

    def __init__(self, message: str, *, details: Optional[List[str]] = None) -> None:
        super().__init__(message)
        self.details = details or []


class PolicyViolationError(Exception):
    """Raised when generated copy violates advisor language policy."""

    def __init__(self, message: str, *, violations: Optional[List[str]] = None) -> None:
        super().__init__(message)
        self.violations = violations or []


def context_payload_snapshot(context: AdvisorContext) -> Dict[str, Any]:
    """Serialize context layers for deterministic observation IDs."""
    return {
        "application_fingerprint": context.application_fingerprint,
        "knowledge": context.knowledge_profile.model_dump(mode="json"),
        "regression": context.regression_report.model_dump(mode="json"),
    }
