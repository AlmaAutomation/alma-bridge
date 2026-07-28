"""LLM request/response models for bounded advisor rendering."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


ADVISOR_LLM_SCHEMA_VERSION = "compatibility_advisor_llm_v1"

POLICY_CONSTRAINTS = (
    "Do not add new observations or facts beyond the supplied deterministic content.",
    "Do not recommend strategies, remediation, or dependency installation.",
    "Do not claim runtime requirements or that the application is broken.",
    "Do not use imperative language such as 'use', 'switch to', 'fix by', or 'you should'.",
    "Preserve verification and severity meaning; rewrite wording only.",
    "Reference only the provided observation_id and evidence_reference_id values.",
)


class AdvisorLLMObservationInput(BaseModel):
    observation_id: str
    category: str
    title: str
    statement: str
    severity: str
    evidence_reference_ids: List[str] = Field(default_factory=list)


class AdvisorLLMRequest(BaseModel):
    schema_version: str = ADVISOR_LLM_SCHEMA_VERSION
    application_name: str
    deterministic_summary: str
    observations: List[AdvisorLLMObservationInput] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    policy_constraints: List[str] = Field(default_factory=lambda: list(POLICY_CONSTRAINTS))


class RenderedObservation(BaseModel):
    observation_id: str
    statement: str
    evidence_reference_ids: List[str] = Field(default_factory=list)

    @field_validator("evidence_reference_ids")
    @classmethod
    def _sort_ids(cls, value: List[str]) -> List[str]:
        return sorted(value)


class RenderedAdvisorExplanation(BaseModel):
    summary: str
    observations: List[RenderedObservation] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)

    @field_validator("observations")
    @classmethod
    def _sort_observations(cls, value: List[RenderedObservation]) -> List[RenderedObservation]:
        return sorted(value, key=lambda item: item.observation_id)


class AdvisorLLMResponse(BaseModel):
    rendered: RenderedAdvisorExplanation
    raw_text: Optional[str] = None
