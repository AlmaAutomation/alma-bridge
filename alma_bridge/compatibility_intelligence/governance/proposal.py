"""Create promotion proposals from calibration evidence."""

from __future__ import annotations

from typing import List, Optional

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.compatibility_intelligence.behavior_requirements import get_behavior_profile
from alma_bridge.compatibility_intelligence.calibration_repository import _utc_now_iso
from alma_bridge.compatibility_intelligence.calibration_service import CalibrationService
from alma_bridge.compatibility_intelligence.models import CalibrationClassification

from alma_bridge.compatibility_intelligence.governance.digest import compute_proposal_digest
from alma_bridge.compatibility_intelligence.governance.errors import (
    PolicyViolationError,
    ScopeMismatchError,
)
from alma_bridge.compatibility_intelligence.governance.models import (
    CapabilityMaturityState,
    CapabilityScope,
    PromotionProposal,
)
from alma_bridge.compatibility_intelligence.governance.policy import (
    PromotionEvidence,
    evaluate_promotion_policy,
)
from alma_bridge.compatibility_intelligence.governance.repository import GovernanceRepository


def _aggregate_calibration(
    calibration: CalibrationService,
    *,
    provider_id: str,
    capability_id: str,
    application_scope: Optional[List[str]] = None,
) -> dict:
    records = calibration.list_records_for_capability(capability_id)
    records = [r for r in records if r.get("provider_id") == provider_id]

    counts = {
        "verified_success_count": 0,
        "verified_failure_count": 0,
        "false_positive_count": 0,
        "false_negative_count": 0,
        "indeterminate_count": 0,
        "supporting_calibration_records": [],
        "behavior_scenarios": [],
        "behavior_gaps": [],
        "unresolved_false_positives": 0,
    }

    repo = calibration._repo
    for record in records:
        snap = repo.get_snapshot(str(record.get("snapshot_id", "")))
        if snap is None:
            continue
        if application_scope:
            fixture_match = any(
                f in snap.analysis_digest or f in snap.binary_digest
                for f in application_scope
            )
            if not fixture_match and snap.required_capabilities:
                pass

        cls = record.get("classification", "")
        counts["supporting_calibration_records"].append(str(record.get("record_id", "")))
        gaps = record.get("behavior_gaps") or []
        counts["behavior_gaps"].extend(gaps)
        if cls == CalibrationClassification.TRUE_POSITIVE.value:
            counts["verified_success_count"] += 1
        elif cls == CalibrationClassification.FALSE_POSITIVE.value:
            counts["false_positive_count"] += 1
            attr = record.get("failure_attribution")
            if not attr or attr == "unknown":
                counts["unresolved_false_positives"] += 1
        elif cls == CalibrationClassification.FALSE_NEGATIVE.value:
            counts["false_negative_count"] += 1
        elif cls == CalibrationClassification.TRUE_NEGATIVE.value:
            counts["verified_failure_count"] += 1
        else:
            counts["indeterminate_count"] += 1

        for gap in gaps:
            if gap.startswith("behavior:"):
                counts["behavior_scenarios"].append(gap.replace("behavior:", ""))

    counts["behavior_scenarios"] = sorted(set(counts["behavior_scenarios"]))
    counts["behavior_gaps"] = sorted(set(counts["behavior_gaps"]))
    counts["supporting_calibration_records"] = sorted(
        set(counts["supporting_calibration_records"])
    )
    return counts


def create_proposal(
    *,
    provider_id: str,
    capability_id: str,
    proposed_state: CapabilityMaturityState,
    scope: Optional[CapabilityScope] = None,
    behavior_scenarios: Optional[List[str]] = None,
    application_scope: Optional[List[str]] = None,
    governance_repo: Optional[GovernanceRepository] = None,
    calibration: Optional[CalibrationService] = None,
    security_review_complete: bool = False,
    regression_suite_stable: bool = False,
    explicit_human_approval: bool = False,
) -> PromotionProposal:
    """Create a promotion proposal from calibration evidence — does not apply."""
    gov = governance_repo or GovernanceRepository()
    cal = calibration or CalibrationService()
    registry = gov.get_current_version()

    profile = get_behavior_profile(capability_id, provider_id)
    resolved_scope = scope or CapabilityScope(
        provider_id=provider_id,
        provider_version=profile.implementation_version if profile else "0.2.0-m2",
        capability_id=capability_id,
        behavior_profile=behavior_scenarios or (profile.supported_behaviors if profile else []),
        application_scope=application_scope or [],
        implementation_version=profile.implementation_version if profile else "",
    )

    if resolved_scope.provider_id != provider_id or resolved_scope.capability_id != capability_id:
        raise ScopeMismatchError("proposal scope must match provider and capability")

    entry = gov.find_maturity(resolved_scope)
    current_state = entry.maturity_state if entry else CapabilityMaturityState.DECLARED

    agg = _aggregate_calibration(
        cal,
        provider_id=provider_id,
        capability_id=capability_id,
        application_scope=application_scope,
    )

    scenarios = behavior_scenarios or agg["behavior_scenarios"]
    if profile:
        scenarios = sorted(set(scenarios) | set(profile.verified_scenarios))

    limitations = list(profile.limitations) if profile else []
    evidence_refs = list(profile.evidence_references) if profile else []

    evidence = PromotionEvidence(
        scope=resolved_scope,
        current_state=current_state,
        proposed_state=proposed_state,
        verified_success_count=agg["verified_success_count"],
        verified_failure_count=agg["verified_failure_count"],
        false_positive_count=agg["false_positive_count"],
        false_negative_count=agg["false_negative_count"],
        indeterminate_count=agg["indeterminate_count"],
        behavior_scenarios=scenarios,
        required_behavior_scenarios=profile.verified_scenarios if profile else [],
        behavior_gaps=agg["behavior_gaps"],
        unresolved_false_positives=agg["unresolved_false_positives"],
        supporting_record_count=len(agg["supporting_calibration_records"]),
        security_review_complete=security_review_complete,
        regression_suite_stable=regression_suite_stable,
        explicit_human_approval=explicit_human_approval,
        limitations=limitations,
    )

    policy = evaluate_promotion_policy(evidence)
    if not policy.allowed and proposed_state not in (
        CapabilityMaturityState.DEPRECATED,
        CapabilityMaturityState.REVOKED,
    ):
        raise PolicyViolationError("; ".join(policy.reasons))

    ts = _utc_now_iso()
    proposal_id = sha256_v1(
        {
            "provider_id": provider_id,
            "capability_id": capability_id,
            "proposed_state": proposed_state.value,
            "scope": resolved_scope.scope_key(),
            "registry_version": registry.version_id,
            "created_at": ts,
        }
    )[:16]

    proposal = PromotionProposal(
        proposal_id=f"gov_prop_{proposal_id}",
        provider_id=provider_id,
        capability_id=capability_id,
        current_state=current_state,
        proposed_state=proposed_state,
        scope=resolved_scope,
        supporting_calibration_records=agg["supporting_calibration_records"],
        verified_success_count=agg["verified_success_count"],
        verified_failure_count=agg["verified_failure_count"],
        false_positive_count=agg["false_positive_count"],
        false_negative_count=agg["false_negative_count"],
        indeterminate_count=agg["indeterminate_count"],
        behavior_scenarios=scenarios,
        evidence_references=evidence_refs,
        limitations=limitations,
        registry_version=registry.version_id,
        proposal_digest="",
        created_at=ts,
    )
    digest = compute_proposal_digest(proposal)
    return proposal.model_copy(update={"proposal_digest": digest})
