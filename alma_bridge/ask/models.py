"""Domain models for Ask Alma evidence-grounded Q&A."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


ASK_SCHEMA_VERSION = "compatibility_ask_v1"
ASK_ENGINE_VERSION = "compatibility_ask_deterministic_v1"


class QuestionType(str, Enum):
    COMPATIBILITY_SUMMARY = "compatibility_summary"
    VERIFICATION_HISTORY = "verification_history"
    FRAMEWORK_HISTORY = "framework_history"
    LAUNCH_STRATEGY_HISTORY = "launch_strategy_history"
    RUNTIME_OBSERVATIONS = "runtime_observations"
    REGRESSION_CHANGES = "regression_changes"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    EVIDENCE_PROVENANCE = "evidence_provenance"
    REMEDIATION_REFUSAL = "remediation_refusal"
    STRATEGY_RECOMMENDATION_REFUSAL = "strategy_recommendation_refusal"
    UNSUPPORTED = "unsupported"


class AskAlmaQuestion(BaseModel):
    question: str
    application_fingerprint: str
    session_id: Optional[str] = None
    render: str = "deterministic"

    @field_validator("question")
    @classmethod
    def _strip_question(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("question is required")
        return text


class AskAlmaEvidenceReference(BaseModel):
    source_layer: str
    source_type: str
    source_id: str
    session_id: Optional[str] = None
    attempt_id: Optional[int] = None
    artifact_key: str = ""

    @field_validator("source_type", "source_id", "source_layer")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("evidence reference fields require non-empty values")
        return value


class AskAlmaAnswer(BaseModel):
    question: str
    question_type: QuestionType
    answer: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    evidence_references: List[AskAlmaEvidenceReference] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    render_mode: str = "deterministic"
    fallback_reason: Optional[str] = None
    schema_version: str = ASK_SCHEMA_VERSION
    engine_version: str = ASK_ENGINE_VERSION
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @field_validator("evidence_references")
    @classmethod
    def _require_provenance(
        cls,
        value: List[AskAlmaEvidenceReference],
    ) -> List[AskAlmaEvidenceReference]:
        return sorted(
            value,
            key=lambda ref: (ref.source_layer, ref.source_type, ref.source_id, ref.artifact_key),
        )

    @field_validator("limitations")
    @classmethod
    def _sort_limitations(cls, value: List[str]) -> List[str]:
        return sorted(value)


class AskAlmaContext(BaseModel):
    application_fingerprint: str
    application_name: str
    session_id: Optional[str] = None
    question_type: QuestionType
    knowledge_profile: Optional[dict] = None
    regression_report: Optional[dict] = None
    advisor_explanation: Optional[dict] = None


class AskAlmaNotFoundError(Exception):
    """Raised when no evidence exists for the requested application/session."""


class AskAlmaValidationError(Exception):
    """Raised when answer generation or validation fails."""

    def __init__(self, message: str, *, details: Optional[List[str]] = None) -> None:
        super().__init__(message)
        self.details = details or []
