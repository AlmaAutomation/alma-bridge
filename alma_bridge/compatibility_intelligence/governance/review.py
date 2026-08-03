"""Human review workflow for promotion proposals."""

from __future__ import annotations

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.compatibility_intelligence.calibration_repository import _utc_now_iso

from alma_bridge.compatibility_intelligence.governance.digest import compute_review_binding_digest
from alma_bridge.compatibility_intelligence.governance.errors import ProposalNotApprovedError
from alma_bridge.compatibility_intelligence.governance.models import (
    PromotionProposal,
    ProposalReview,
    ProposalReviewState,
)
from alma_bridge.compatibility_intelligence.governance.repository import GovernanceRepository


def submit_review(
    proposal: PromotionProposal,
    *,
    reviewer: str,
    state: ProposalReviewState,
    rationale: str = "",
    repository: GovernanceRepository | None = None,
) -> ProposalReview:
    """Record a human-authored review bound to exact proposal digest."""
    if not (reviewer or "").strip():
        raise ProposalNotApprovedError("reviewer identity required")

    ts = _utc_now_iso()
    review_id = sha256_v1(
        {
            "proposal_id": proposal.proposal_id,
            "proposal_digest": proposal.proposal_digest,
            "reviewer": reviewer,
            "state": state.value,
            "created_at": ts,
        }
    )[:16]

    review = ProposalReview(
        review_id=f"gov_rev_{review_id}",
        proposal_id=proposal.proposal_id,
        proposal_digest=proposal.proposal_digest,
        state=state,
        reviewer=reviewer.strip(),
        rationale=rationale,
        created_at=ts,
    )
    binding = compute_review_binding_digest(
        proposal.proposal_digest, review.reviewer, review.state.value
    )
    repo = repository or GovernanceRepository()
    repo.save_review({**review.model_dump(mode="json"), "binding_digest": binding})
    return review


def find_approved_review(
    proposal_id: str,
    proposal_digest: str,
    repository: GovernanceRepository | None = None,
) -> ProposalReview | None:
    """Find the latest approved review matching proposal digest."""
    repo = repository or GovernanceRepository()
    for data in repo.list_reviews_for_proposal(proposal_id):
        if (
            data.get("state") == ProposalReviewState.APPROVED.value
            and data.get("proposal_digest") == proposal_digest
        ):
            return ProposalReview.model_validate(data)
    return None
