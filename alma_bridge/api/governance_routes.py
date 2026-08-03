"""HTTP routes for capability registry governance."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from alma_bridge.compatibility_intelligence.governance.errors import (
    GovernanceError,
    PolicyViolationError,
    ProposalNotApprovedError,
    StaleProposalError,
)
from alma_bridge.compatibility_intelligence.governance.models import (
    CapabilityMaturityState,
    CapabilityScope,
    ProposalReviewState,
)
from alma_bridge.compatibility_intelligence.governance.service import GovernanceService

router = APIRouter()
_service = GovernanceService()


class CreateProposalRequest(BaseModel):
    provider_id: str
    capability_id: str
    proposed_state: CapabilityMaturityState
    behavior_scenarios: List[str] = Field(default_factory=list)
    application_scope: List[str] = Field(default_factory=list)
    provider_version: str = ""
    architecture: str = "x64"
    implementation_version: str = ""
    security_review_complete: bool = False
    regression_suite_stable: bool = False
    explicit_human_approval: bool = False


class ReviewProposalRequest(BaseModel):
    reviewer: str
    state: ProposalReviewState
    rationale: str = ""
    proposal_digest: Optional[str] = None


class ApplyProposalRequest(BaseModel):
    proposal_digest: str


@router.get(
    "/bridge/compatibility/governance/proposals",
    tags=["Compatibility Intelligence Governance"],
)
def list_proposals(limit: int = 50):
    """List promotion proposals — read-only, no execution."""
    return _service.list_proposals(limit=limit)


@router.get(
    "/bridge/compatibility/governance/proposals/{proposal_id}",
    tags=["Compatibility Intelligence Governance"],
)
def get_proposal(proposal_id: str):
    proposal = _service.get_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"Proposal not found: {proposal_id}")
    return proposal


@router.get(
    "/bridge/compatibility/governance/registry",
    tags=["Compatibility Intelligence Governance"],
)
def get_registry():
    """Current versioned capability maturity registry."""
    version = _service.get_current_registry()
    return version.model_dump(mode="json")


@router.get(
    "/bridge/compatibility/governance/registry/versions",
    tags=["Compatibility Intelligence Governance"],
)
def list_registry_versions():
    versions = _service.list_registry_versions()
    return [
        {
            "version_id": v.version_id,
            "parent_version_id": v.parent_version_id,
            "created_at": v.created_at,
            "digest": v.digest,
            "entry_count": len(v.entries),
            "change_summary": v.change_summary,
        }
        for v in versions
    ]


@router.post(
    "/bridge/compatibility/governance/proposals",
    tags=["Compatibility Intelligence Governance"],
)
def create_proposal(request: CreateProposalRequest):
    """Create proposal from calibration evidence — does NOT auto-apply."""
    scope = CapabilityScope(
        provider_id=request.provider_id,
        provider_version=request.provider_version,
        capability_id=request.capability_id,
        behavior_profile=request.behavior_scenarios,
        architecture=request.architecture,
        application_scope=request.application_scope,
        implementation_version=request.implementation_version,
    )
    try:
        proposal = _service.create_proposal_from_evidence(
            provider_id=request.provider_id,
            capability_id=request.capability_id,
            proposed_state=request.proposed_state,
            scope=scope,
            behavior_scenarios=request.behavior_scenarios,
            application_scope=request.application_scope,
            security_review_complete=request.security_review_complete,
            regression_suite_stable=request.regression_suite_stable,
            explicit_human_approval=request.explicit_human_approval,
        )
        return proposal.model_dump(mode="json")
    except PolicyViolationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GovernanceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/bridge/compatibility/governance/proposals/{proposal_id}/reviews",
    tags=["Compatibility Intelligence Governance"],
)
def review_proposal(proposal_id: str, request: ReviewProposalRequest):
    """Submit human review bound to proposal digest."""
    try:
        review = _service.review_proposal(
            proposal_id,
            reviewer=request.reviewer,
            state=request.state,
            rationale=request.rationale,
            proposal_digest=request.proposal_digest,
        )
        return review.model_dump(mode="json")
    except ProposalNotApprovedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/bridge/compatibility/governance/proposals/{proposal_id}/apply",
    tags=["Compatibility Intelligence Governance"],
)
def apply_proposal(proposal_id: str, request: ApplyProposalRequest):
    """Apply approved proposal to versioned registry only — no execution."""
    try:
        version = _service.apply_proposal(
            proposal_id,
            proposal_digest=request.proposal_digest,
        )
        return version.model_dump(mode="json")
    except StaleProposalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ProposalNotApprovedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PolicyViolationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GovernanceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
