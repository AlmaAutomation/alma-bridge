"""Deterministic proposal and review digest computation."""

from __future__ import annotations

from alma_bridge.compatibility.profile_fingerprints import sha256_v1

from alma_bridge.compatibility_intelligence.governance.models import PromotionProposal


def compute_proposal_digest(proposal: PromotionProposal) -> str:
    """Compute deterministic digest for a promotion proposal."""
    payload = {
        "provider_id": proposal.provider_id,
        "capability_id": proposal.capability_id,
        "current_state": proposal.current_state.value,
        "proposed_state": proposal.proposed_state.value,
        "scope": proposal.scope.model_dump(mode="json"),
        "supporting_calibration_records": sorted(proposal.supporting_calibration_records),
        "verified_success_count": proposal.verified_success_count,
        "verified_failure_count": proposal.verified_failure_count,
        "false_positive_count": proposal.false_positive_count,
        "false_negative_count": proposal.false_negative_count,
        "indeterminate_count": proposal.indeterminate_count,
        "behavior_scenarios": sorted(proposal.behavior_scenarios),
        "evidence_references": sorted(proposal.evidence_references),
        "limitations": sorted(proposal.limitations),
        "registry_version": proposal.registry_version,
    }
    return sha256_v1(payload)


def compute_review_binding_digest(proposal_digest: str, reviewer: str, state: str) -> str:
    return sha256_v1({"proposal_digest": proposal_digest, "reviewer": reviewer, "state": state})
