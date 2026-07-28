"""Evidence reference ID helpers for LLM citation validation."""

from __future__ import annotations

from alma_bridge.advisor.models import AdvisorExplanation, AdvisorObservation
from alma_bridge.advisor.llm.models import (
    AdvisorLLMObservationInput,
    AdvisorLLMRequest,
    POLICY_CONSTRAINTS,
)
from alma_bridge.knowledge.models import KnowledgeEvidenceReference


def build_evidence_reference_id(ref: KnowledgeEvidenceReference) -> str:
    artifact = ref.artifact_key or ""
    return f"{ref.source_type}:{ref.source_id}:{artifact}"


def evidence_ids_for_observation(observation: AdvisorObservation) -> list[str]:
    return sorted(build_evidence_reference_id(ref) for ref in observation.evidence_references)


def build_llm_request(explanation: AdvisorExplanation) -> AdvisorLLMRequest:
    observations = [
        AdvisorLLMObservationInput(
            observation_id=obs.observation_id,
            category=obs.category.value,
            title=obs.title,
            statement=obs.statement,
            severity=obs.severity,
            evidence_reference_ids=evidence_ids_for_observation(obs),
        )
        for obs in explanation.observations
    ]
    return AdvisorLLMRequest(
        application_name=explanation.application_name,
        deterministic_summary=explanation.summary,
        observations=observations,
        limitations=list(explanation.limitations),
        policy_constraints=list(POLICY_CONSTRAINTS),
    )
