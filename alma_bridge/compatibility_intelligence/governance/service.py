"""Governance orchestration — proposals, reviews, registry application."""

from __future__ import annotations

from typing import List, Optional

from alma_bridge.compatibility_intelligence.behavior_requirements import get_behavior_profile
from alma_bridge.compatibility_intelligence.calibration_service import CalibrationService

from alma_bridge.compatibility_intelligence.governance.digest import compute_proposal_digest
from alma_bridge.compatibility_intelligence.governance.errors import (
    EvidenceResolutionError,
    PolicyViolationError,
    ProposalNotApprovedError,
    StaleProposalError,
)
from alma_bridge.compatibility_intelligence.governance.models import (
    CapabilityMaturityEntry,
    CapabilityMaturityState,
    CapabilityScope,
    PromotionProposal,
    ProposalReview,
    ProposalReviewState,
    RegistryVersion,
)
from alma_bridge.compatibility_intelligence.governance.policy import (
    PromotionEvidence,
    assert_promotion_allowed,
)
from alma_bridge.compatibility_intelligence.governance.proposal import create_proposal
from alma_bridge.compatibility_intelligence.governance.repository import GovernanceRepository
from alma_bridge.compatibility_intelligence.governance.review import (
    find_approved_review,
    submit_review,
)


class GovernanceService:
    """Orchestrate human-gated capability maturity promotion."""

    def __init__(
        self,
        repository: Optional[GovernanceRepository] = None,
        calibration: Optional[CalibrationService] = None,
    ) -> None:
        self._repo = repository or GovernanceRepository()
        self._calibration = calibration or CalibrationService()

    def get_current_registry(self) -> RegistryVersion:
        return self._repo.get_current_version()

    def list_registry_versions(self) -> List[RegistryVersion]:
        return self._repo.list_versions()

    def list_proposals(self, limit: int = 100) -> List[dict]:
        return self._repo.list_proposals(limit=limit)

    def get_proposal(self, proposal_id: str) -> Optional[dict]:
        data = self._repo.get_proposal(proposal_id)
        if data is None:
            return None
        reviews = self._repo.list_reviews_for_proposal(proposal_id)
        return {**data, "reviews": reviews}

    def create_proposal_from_evidence(
        self,
        *,
        provider_id: str,
        capability_id: str,
        proposed_state: CapabilityMaturityState,
        scope: Optional[CapabilityScope] = None,
        behavior_scenarios: Optional[List[str]] = None,
        application_scope: Optional[List[str]] = None,
        security_review_complete: bool = False,
        regression_suite_stable: bool = False,
        explicit_human_approval: bool = False,
    ) -> PromotionProposal:
        proposal = create_proposal(
            provider_id=provider_id,
            capability_id=capability_id,
            proposed_state=proposed_state,
            scope=scope,
            behavior_scenarios=behavior_scenarios,
            application_scope=application_scope,
            governance_repo=self._repo,
            calibration=self._calibration,
            security_review_complete=security_review_complete,
            regression_suite_stable=regression_suite_stable,
            explicit_human_approval=explicit_human_approval,
        )
        self._repo.save_proposal(proposal.model_dump(mode="json"))
        return proposal

    def review_proposal(
        self,
        proposal_id: str,
        *,
        reviewer: str,
        state: ProposalReviewState,
        rationale: str = "",
        proposal_digest: Optional[str] = None,
    ) -> ProposalReview:
        data = self._repo.get_proposal(proposal_id)
        if data is None:
            raise ProposalNotApprovedError(f"proposal not found: {proposal_id}")
        proposal = PromotionProposal.model_validate(data)
        if proposal_digest and proposal_digest != proposal.proposal_digest:
            raise ProposalNotApprovedError("proposal digest mismatch at review time")
        return submit_review(
            proposal,
            reviewer=reviewer,
            state=state,
            rationale=rationale,
            repository=self._repo,
        )

    def _resolve_evidence(self, proposal: PromotionProposal) -> None:
        for record_id in proposal.supporting_calibration_records:
            found = any(
                r.get("record_id") == record_id for r in self._calibration.list_records()
            )
            if not found:
                raise EvidenceResolutionError(
                    f"supporting calibration record not found: {record_id}"
                )

    def apply_proposal(
        self,
        proposal_id: str,
        *,
        proposal_digest: str,
    ) -> RegistryVersion:
        """Apply an approved proposal — updates versioned registry only."""
        data = self._repo.get_proposal(proposal_id)
        if data is None:
            raise ProposalNotApprovedError(f"proposal not found: {proposal_id}")

        proposal = PromotionProposal.model_validate(data)
        if proposal.proposal_digest != proposal_digest:
            raise ProposalNotApprovedError("proposal digest mismatch at apply time")

        recomputed = compute_proposal_digest(proposal)
        if recomputed != proposal.proposal_digest:
            raise ProposalNotApprovedError("proposal content digest invalid")

        review = find_approved_review(proposal_id, proposal_digest, self._repo)
        if review is None:
            raise ProposalNotApprovedError("no approved review matching proposal digest")

        current = self._repo.get_current_version()
        if current.version_id != proposal.registry_version:
            raise StaleProposalError(
                f"registry version changed: proposal={proposal.registry_version}, "
                f"current={current.version_id}"
            )

        self._resolve_evidence(proposal)

        profile = get_behavior_profile(proposal.capability_id, proposal.provider_id)
        evidence = PromotionEvidence(
            scope=proposal.scope,
            current_state=proposal.current_state,
            proposed_state=proposal.proposed_state,
            verified_success_count=proposal.verified_success_count,
            verified_failure_count=proposal.verified_failure_count,
            false_positive_count=proposal.false_positive_count,
            false_negative_count=proposal.false_negative_count,
            indeterminate_count=proposal.indeterminate_count,
            behavior_scenarios=proposal.behavior_scenarios,
            required_behavior_scenarios=profile.verified_scenarios if profile else [],
            behavior_gaps=[],
            unresolved_false_positives=proposal.false_positive_count,
            supporting_record_count=len(proposal.supporting_calibration_records),
            security_review_complete=True,
            regression_suite_stable=True,
            explicit_human_approval=True,
            limitations=proposal.limitations,
        )
        try:
            assert_promotion_allowed(evidence)
        except PolicyViolationError:
            if proposal.proposed_state not in (
                CapabilityMaturityState.DEPRECATED,
                CapabilityMaturityState.REVOKED,
            ):
                raise

        new_entries: List[CapabilityMaturityEntry] = []
        updated = False
        for entry in current.entries:
            if entry.scope.scope_key() == proposal.scope.scope_key():
                new_entries.append(
                    CapabilityMaturityEntry(
                        scope=entry.scope,
                        maturity_state=proposal.proposed_state,
                        limitations=list(proposal.limitations) or list(entry.limitations),
                        evidence_references=sorted(
                            set(entry.evidence_references) | set(proposal.evidence_references)
                        ),
                        supported_behaviors=list(entry.supported_behaviors),
                        unsupported_behaviors=list(entry.unsupported_behaviors),
                    )
                )
                updated = True
            else:
                new_entries.append(entry)

        if not updated:
            profile = get_behavior_profile(proposal.capability_id, proposal.provider_id)
            new_entries.append(
                CapabilityMaturityEntry(
                    scope=proposal.scope,
                    maturity_state=proposal.proposed_state,
                    limitations=list(proposal.limitations),
                    evidence_references=list(proposal.evidence_references),
                    supported_behaviors=list(profile.supported_behaviors) if profile else [],
                    unsupported_behaviors=list(profile.unsupported_behaviors) if profile else [],
                )
            )

        return self._repo.append_version(
            new_entries,
            parent_version_id=current.version_id,
            change_summary=(
                f"Applied proposal {proposal_id}: "
                f"{proposal.current_state.value} -> {proposal.proposed_state.value} "
                f"for {proposal.provider_id}/{proposal.capability_id}"
            ),
        )

    def rollback_to_version(self, version_id: str) -> RegistryVersion:
        """Rollback by creating a new registry version from a historical snapshot."""
        source = self._repo.get_version(version_id)
        current = self._repo.get_current_version()
        if source.version_id == current.version_id:
            return current
        return self._repo.append_version(
            list(source.entries),
            parent_version_id=current.version_id,
            change_summary=f"Rollback to {version_id}",
        )
