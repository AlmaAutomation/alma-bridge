"""Read-only Compatibility Advisor — deterministic explanations from existing layers."""

from alma_bridge.advisor.models import (
    ADVISOR_ENGINE_VERSION,
    ADVISOR_SCHEMA_VERSION,
    AdvisorContext,
    AdvisorExplanation,
    AdvisorExplanationResponse,
    AdvisorNotFoundError,
    AdvisorObservation,
    MalformedAdvisorError,
    PolicyViolationError,
)
from alma_bridge.advisor.service import CompatibilityAdvisorService

__all__ = [
    "ADVISOR_ENGINE_VERSION",
    "ADVISOR_SCHEMA_VERSION",
    "AdvisorContext",
    "AdvisorExplanation",
    "AdvisorExplanationResponse",
    "AdvisorNotFoundError",
    "AdvisorObservation",
    "CompatibilityAdvisorService",
    "MalformedAdvisorError",
    "PolicyViolationError",
]
