"""Governance models — capability maturity states, proposals, reviews, registry versions."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

ACI_GOVERNANCE_SCHEMA_VERSION = "compatibility_intelligence_governance_v1"
GOVERNANCE_REGISTRY_SEED_VERSION = "aci_governance_registry_v1"
GOVERNANCE_ENGINE_VERSION = "aci_governance_v1"


class CapabilityMaturityState(str, Enum):
    DECLARED = "declared"
    EXPERIMENTAL = "experimental"
    BEHAVIORALLY_TESTED = "behaviorally_tested"
    CALIBRATION_SUPPORTED = "calibration_supported"
    VERIFIED_BOUNDED = "verified_bounded"
    STABLE = "stable"
    DEPRECATED = "deprecated"
    REVOKED = "revoked"


MATURITY_ORDER = {
    CapabilityMaturityState.DECLARED: 0,
    CapabilityMaturityState.EXPERIMENTAL: 1,
    CapabilityMaturityState.BEHAVIORALLY_TESTED: 2,
    CapabilityMaturityState.CALIBRATION_SUPPORTED: 3,
    CapabilityMaturityState.VERIFIED_BOUNDED: 4,
    CapabilityMaturityState.STABLE: 5,
    CapabilityMaturityState.DEPRECATED: -1,
    CapabilityMaturityState.REVOKED: -2,
}


class CapabilityScope(BaseModel):
    """Scoped capability identity — maturity is never global from one fixture."""

    provider_id: str
    provider_version: str = ""
    capability_id: str
    behavior_profile: List[str] = Field(default_factory=list)
    architecture: str = "x64"
    application_scope: List[str] = Field(default_factory=list)
    implementation_version: str = ""

    @field_validator("provider_id", "capability_id")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("scope requires non-empty provider_id and capability_id")
        return value.strip()

    def scope_key(self) -> str:
        parts = [
            self.provider_id,
            self.provider_version or "*",
            self.capability_id,
            ",".join(sorted(self.behavior_profile)) or "*",
            self.architecture,
            ",".join(sorted(self.application_scope)) or "*",
            self.implementation_version or "*",
        ]
        return "|".join(parts)


class CapabilityMaturityEntry(BaseModel):
    scope: CapabilityScope
    maturity_state: CapabilityMaturityState
    limitations: List[str] = Field(default_factory=list)
    evidence_references: List[str] = Field(default_factory=list)
    supported_behaviors: List[str] = Field(default_factory=list)
    unsupported_behaviors: List[str] = Field(default_factory=list)


class RegistryVersion(BaseModel):
    """Append-only versioned capability maturity registry."""

    schema_version: str = ACI_GOVERNANCE_SCHEMA_VERSION
    version_id: str
    parent_version_id: Optional[str] = None
    created_at: str
    digest: str
    entries: List[CapabilityMaturityEntry] = Field(default_factory=list)
    change_summary: str = ""
    engine_version: str = GOVERNANCE_ENGINE_VERSION


class PromotionProposal(BaseModel):
    """Evidence-derived promotion proposal — does not auto-apply."""

    schema_version: str = ACI_GOVERNANCE_SCHEMA_VERSION
    proposal_id: str
    provider_id: str
    capability_id: str
    current_state: CapabilityMaturityState
    proposed_state: CapabilityMaturityState
    scope: CapabilityScope
    supporting_calibration_records: List[str] = Field(default_factory=list)
    verified_success_count: int = 0
    verified_failure_count: int = 0
    false_positive_count: int = 0
    false_negative_count: int = 0
    indeterminate_count: int = 0
    behavior_scenarios: List[str] = Field(default_factory=list)
    evidence_references: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    registry_version: str
    proposal_digest: str
    created_at: str
    engine_version: str = GOVERNANCE_ENGINE_VERSION


class ProposalReviewState(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"


class ProposalReview(BaseModel):
    """Human-authored review bound to exact proposal digest."""

    schema_version: str = ACI_GOVERNANCE_SCHEMA_VERSION
    review_id: str
    proposal_id: str
    proposal_digest: str
    state: ProposalReviewState
    reviewer: str
    rationale: str = ""
    created_at: str
    engine_version: str = GOVERNANCE_ENGINE_VERSION
