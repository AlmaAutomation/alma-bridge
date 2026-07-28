"""Validate bounded LLM output against deterministic advisor explanations."""

from __future__ import annotations

import re
from typing import Dict, List, Set

from alma_bridge.advisor.llm.models import RenderedAdvisorExplanation, RenderedObservation
from alma_bridge.advisor.llm.queries import build_evidence_reference_id, evidence_ids_for_observation
from alma_bridge.advisor.models import AdvisorExplanation, AdvisorObservation
from alma_bridge.advisor.policy import validate_statement


class AdvisorValidationError(Exception):
    """Raised when LLM output fails bounded validation."""

    def __init__(self, reason: str, *, details: List[str] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.details = details or []


# Semantic anchors that must not flip between deterministic and rendered copy.
_VERIFIED_SUCCESS_MARKERS = ("authoritatively verified successful", "verified success")
_VERIFIED_FAILURE_MARKERS = ("verified failure", "authoritative verified failure")
_UNVERIFIABLE_MARKERS = ("unverifiable",)
_CONFLICT_MARKERS = ("conflicting", "conflict")
_RUNTIME_REQUIREMENT_MARKERS = (
    "requires vc++",
    "requires runtime",
    "must install",
    "has a runtime requirement",
    "runtime requirement for",
)


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in markers)


class AdvisorOutputValidator:
    """Ensure LLM rendering preserves deterministic meaning and provenance."""

    def validate(
        self,
        deterministic: AdvisorExplanation,
        rendered: RenderedAdvisorExplanation,
    ) -> RenderedAdvisorExplanation:
        deterministic_by_id: Dict[str, AdvisorObservation] = {
            obs.observation_id: obs for obs in deterministic.observations
        }
        rendered_by_id: Dict[str, RenderedObservation] = {
            obs.observation_id: obs for obs in rendered.observations
        }

        deterministic_ids = set(deterministic_by_id)
        rendered_ids = set(rendered_by_id)
        if rendered_ids - deterministic_ids:
            unknown = sorted(rendered_ids - deterministic_ids)
            raise AdvisorValidationError(
                "unknown_observation_id",
                details=[f"unknown observation ids: {', '.join(unknown)}"],
            )
        if rendered_ids != deterministic_ids:
            missing = sorted(deterministic_ids - rendered_ids)
            raise AdvisorValidationError(
                "missing_observation_id",
                details=[f"missing observation ids: {', '.join(missing)}"],
            )

        violations: List[str] = []
        violations.extend(validate_statement(rendered.summary))
        if _contains_any(rendered.summary.lower(), _RUNTIME_REQUIREMENT_MARKERS):
            violations.append("summary: runtime requirement claim introduced")
        for limitation in rendered.limitations:
            violations.extend(validate_statement(limitation))

        for obs_id, rendered_obs in rendered_by_id.items():
            source = deterministic_by_id[obs_id]
            violations.extend(self._validate_rendered_observation(source, rendered_obs))

        if violations:
            raise AdvisorValidationError(
                "policy_validation_failed",
                details=sorted(set(violations)),
            )
        return rendered

    def _validate_rendered_observation(
        self,
        source: AdvisorObservation,
        rendered: RenderedObservation,
    ) -> List[str]:
        violations = validate_statement(rendered.statement)
        allowed_evidence = set(evidence_ids_for_observation(source))
        rendered_evidence = set(rendered.evidence_reference_ids)
        if not rendered_evidence:
            violations.append(f"{source.observation_id}: missing evidence references")
        if rendered_evidence - allowed_evidence:
            violations.append(f"{source.observation_id}: unknown evidence reference ids")
        if allowed_evidence - rendered_evidence:
            violations.append(f"{source.observation_id}: removed required evidence references")

        source_text = source.statement.lower()
        rendered_text = rendered.statement.lower()

        if _contains_any(source_text, _VERIFIED_SUCCESS_MARKERS) and not _contains_any(
            rendered_text, _VERIFIED_SUCCESS_MARKERS
        ):
            violations.append(f"{source.observation_id}: verification success semantics changed")
        if _contains_any(source_text, _VERIFIED_FAILURE_MARKERS) and not _contains_any(
            rendered_text, _VERIFIED_FAILURE_MARKERS
        ):
            violations.append(f"{source.observation_id}: verification failure semantics changed")
        if _contains_any(source_text, _UNVERIFIABLE_MARKERS) and not _contains_any(
            rendered_text, _UNVERIFIABLE_MARKERS
        ):
            violations.append(f"{source.observation_id}: unverifiable semantics changed")
        if _contains_any(source_text, _CONFLICT_MARKERS) and not _contains_any(
            rendered_text, _CONFLICT_MARKERS
        ):
            violations.append(f"{source.observation_id}: conflict semantics changed")

        if _contains_any(rendered_text, _RUNTIME_REQUIREMENT_MARKERS):
            violations.append(f"{source.observation_id}: runtime requirement claim introduced")

        invented_framework = self._invented_framework_claim(source_text, rendered_text)
        if invented_framework:
            violations.append(f"{source.observation_id}: invented framework claim")

        return violations

    @staticmethod
    def _invented_framework_claim(source_text: str, rendered_text: str) -> bool:
        framework_pattern = re.compile(r"\b(qt|wxwidgets|electron|gtk|flutter)\b", re.IGNORECASE)
        source_frameworks = {m.lower() for m in framework_pattern.findall(source_text)}
        rendered_frameworks = {m.lower() for m in framework_pattern.findall(rendered_text)}
        return bool(rendered_frameworks - source_frameworks)
