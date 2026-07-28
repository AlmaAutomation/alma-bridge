"""Domain models for Compatibility Knowledge aggregation."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


KNOWLEDGE_SCHEMA_VERSION = "compatibility_knowledge_v1"
AGGREGATION_ENGINE_VERSION = "compatibility_knowledge_aggregation_v1"

VALID_EVIDENCE_CLASSIFICATIONS = frozenset({"observed", "repeated", "conflicting"})


class EvidenceClassification(str, Enum):
    OBSERVED = "observed"
    REPEATED = "repeated"
    CONFLICTING = "conflicting"


class KnowledgeEvidenceReference(BaseModel):
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION
    source_type: str
    source_id: str
    artifact_key: str = ""
    session_id: Optional[str] = None
    attempt_id: Optional[int] = None
    captured_at: Optional[str] = None
    excerpt: Optional[str] = None

    @field_validator("source_type")
    @classmethod
    def _require_source_type(cls, value: str) -> str:
        if not value:
            raise ValueError("evidence reference requires source_type")
        return value


class ObservedFramework(BaseModel):
    framework: str
    observation_count: int = Field(ge=0)
    verified_session_count: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    evidence_references: List[KnowledgeEvidenceReference] = Field(default_factory=list)
    classification: EvidenceClassification

    @field_validator("evidence_references")
    @classmethod
    def _require_provenance(
        cls,
        value: List[KnowledgeEvidenceReference],
    ) -> List[KnowledgeEvidenceReference]:
        if not value:
            raise ValueError("observed frameworks require at least one evidence reference")
        return sorted(
            value,
            key=lambda ref: (ref.source_type, ref.source_id, ref.artifact_key),
        )


class ObservedLaunchStrategy(BaseModel):
    strategy: str
    attempts: int = Field(ge=0)
    verified_successes: int = Field(ge=0)
    verified_failures: int = Field(ge=0)
    success_rate: float = Field(ge=0.0, le=1.0, default=0.0)
    evidence_references: List[KnowledgeEvidenceReference] = Field(default_factory=list)

    @field_validator("evidence_references")
    @classmethod
    def _require_provenance(
        cls,
        value: List[KnowledgeEvidenceReference],
    ) -> List[KnowledgeEvidenceReference]:
        if not value:
            raise ValueError("observed launch strategies require at least one evidence reference")
        return sorted(
            value,
            key=lambda ref: (ref.source_type, ref.source_id, ref.artifact_key),
        )


class VerificationContractAggregate(BaseModel):
    contract: str
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    evidence_references: List[KnowledgeEvidenceReference] = Field(default_factory=list)

    @field_validator("evidence_references")
    @classmethod
    def _require_provenance(
        cls,
        value: List[KnowledgeEvidenceReference],
    ) -> List[KnowledgeEvidenceReference]:
        if not value:
            raise ValueError("verification contracts require at least one evidence reference")
        return sorted(
            value,
            key=lambda ref: (ref.source_type, ref.source_id, ref.artifact_key),
        )


class ObservedRuntime(BaseModel):
    runtime: str
    observation_count: int = Field(ge=0)
    verified_success_observation_count: int = Field(ge=0)
    evidence_references: List[KnowledgeEvidenceReference] = Field(default_factory=list)

    @field_validator("evidence_references")
    @classmethod
    def _require_provenance(
        cls,
        value: List[KnowledgeEvidenceReference],
    ) -> List[KnowledgeEvidenceReference]:
        if not value:
            raise ValueError("observed runtimes require at least one evidence reference")
        return sorted(
            value,
            key=lambda ref: (ref.source_type, ref.source_id, ref.artifact_key),
        )


class ObservedEnvironment(BaseModel):
    environment_identity: str
    summary: str
    observation_count: int = Field(ge=0)
    verified_success_count: int = Field(ge=0)
    verified_failure_count: int = Field(ge=0)
    evidence_references: List[KnowledgeEvidenceReference] = Field(default_factory=list)

    @field_validator("evidence_references")
    @classmethod
    def _require_provenance(
        cls,
        value: List[KnowledgeEvidenceReference],
    ) -> List[KnowledgeEvidenceReference]:
        if not value:
            raise ValueError("observed environments require at least one evidence reference")
        return sorted(
            value,
            key=lambda ref: (ref.source_type, ref.source_id, ref.artifact_key),
        )


class KnowledgeConflict(BaseModel):
    relationship: str
    conflict_type: str
    competing_observations: List[str] = Field(default_factory=list)
    evidence_by_side: Dict[str, List[KnowledgeEvidenceReference]] = Field(default_factory=dict)

    @field_validator("competing_observations")
    @classmethod
    def _sort_observations(cls, value: List[str]) -> List[str]:
        return sorted(value)

    @field_validator("evidence_by_side")
    @classmethod
    def _sort_evidence_sides(
        cls,
        value: Dict[str, List[KnowledgeEvidenceReference]],
    ) -> Dict[str, List[KnowledgeEvidenceReference]]:
        return {
            key: sorted(
                refs,
                key=lambda ref: (ref.source_type, ref.source_id, ref.artifact_key),
            )
            for key, refs in sorted(value.items())
        }


class CompatibilityKnowledgeProfile(BaseModel):
    application_fingerprint: str
    application_name: str
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION
    engine_version: str = AGGREGATION_ENGINE_VERSION
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    total_sessions: int = Field(ge=0)
    verified_successes: int = Field(ge=0)
    verified_failures: int = Field(ge=0)
    unverifiable_sessions: int = Field(ge=0)
    observed_frameworks: List[ObservedFramework] = Field(default_factory=list)
    observed_launch_strategies: List[ObservedLaunchStrategy] = Field(default_factory=list)
    verification_contracts: List[VerificationContractAggregate] = Field(default_factory=list)
    observed_runtimes: List[ObservedRuntime] = Field(default_factory=list)
    observed_environments: List[ObservedEnvironment] = Field(default_factory=list)
    conflicts: List[KnowledgeConflict] = Field(default_factory=list)

    @field_validator("observed_frameworks")
    @classmethod
    def _sort_frameworks(cls, value: List[ObservedFramework]) -> List[ObservedFramework]:
        return sorted(value, key=lambda item: item.framework)

    @field_validator("observed_launch_strategies")
    @classmethod
    def _sort_strategies(cls, value: List[ObservedLaunchStrategy]) -> List[ObservedLaunchStrategy]:
        return sorted(value, key=lambda item: item.strategy)

    @field_validator("verification_contracts")
    @classmethod
    def _sort_contracts(
        cls,
        value: List[VerificationContractAggregate],
    ) -> List[VerificationContractAggregate]:
        return sorted(value, key=lambda item: item.contract)

    @field_validator("observed_runtimes")
    @classmethod
    def _sort_runtimes(cls, value: List[ObservedRuntime]) -> List[ObservedRuntime]:
        return sorted(value, key=lambda item: item.runtime)

    @field_validator("observed_environments")
    @classmethod
    def _sort_environments(cls, value: List[ObservedEnvironment]) -> List[ObservedEnvironment]:
        return sorted(value, key=lambda item: item.environment_identity)

    @field_validator("conflicts")
    @classmethod
    def _sort_conflicts(cls, value: List[KnowledgeConflict]) -> List[KnowledgeConflict]:
        return sorted(value, key=lambda item: (item.relationship, item.conflict_type))


class KnowledgeNotFoundError(Exception):
    """Raised when no evidence exists for the requested application."""


class MalformedKnowledgeEvidenceError(Exception):
    """Raised when persisted evidence cannot be aggregated safely."""

    def __init__(self, message: str, *, details: Optional[List[str]] = None) -> None:
        super().__init__(message)
        self.details = details or []
