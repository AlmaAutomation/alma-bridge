"""Create engineering work items from expansion candidates."""

from __future__ import annotations

from typing import List, Optional

from alma_bridge.compatibility_intelligence.expansion.models import RuntimeExpansionCandidate
from alma_bridge.compatibility_intelligence.expansion.service import ExpansionPlanningService
from alma_bridge.native_lab.checklists import generate_checklist
from alma_bridge.native_lab.digest import compute_work_item_id, digest_of
from alma_bridge.native_lab.errors import CandidateNotFoundError, WorkItemAlreadyExistsError
from alma_bridge.native_lab.models import (
    BoundedImpactSnapshot,
    NATIVE_LAB_IMPLEMENTATION_VERSION,
    NativeRuntimeEngineeringWorkItem,
    ObservedDemandSnapshot,
    PriorityDimensionsSnapshot,
    RiskSeverity,
    SecurityReviewItem,
    WorkItemStatus,
)
from alma_bridge.native_lab.work_items import build_acceptance_criteria_for_behavior


def _find_candidate(candidate_id: str) -> RuntimeExpansionCandidate:
    service = ExpansionPlanningService()
    plan = service.generate_plan()
    for candidate in plan.ranked_candidates:
        if candidate.candidate_id == candidate_id:
            return candidate
    raise CandidateNotFoundError(f"Expansion candidate not found: {candidate_id}")


def _candidate_from_behavior(
    provider_id: str,
    capability_id: str,
    behavior_id: str,
) -> Optional[RuntimeExpansionCandidate]:
    service = ExpansionPlanningService()
    plan = service.generate_plan()
    for candidate in plan.ranked_candidates:
        if (
            candidate.provider_id == provider_id
            and candidate.capability_id == capability_id
            and candidate.behavior_id == behavior_id
        ):
            return candidate
    return None


def create_work_item_from_candidate(
    candidate_id: str,
    *,
    title: Optional[str] = None,
    existing_ids: Optional[set[str]] = None,
) -> NativeRuntimeEngineeringWorkItem:
    """Build a scoped engineering work item from an expansion candidate."""
    candidate = _find_candidate(candidate_id)
    work_item_id = compute_work_item_id(
        candidate.provider_id,
        candidate.capability_id,
        candidate.behavior_id or "",
    )
    if existing_ids and work_item_id in existing_ids:
        raise WorkItemAlreadyExistsError(f"Work item already exists: {work_item_id}")

    priority = PriorityDimensionsSnapshot(
        demand_score=candidate.priority.demand_score,
        bounded_impact_score=candidate.priority.bounded_impact_score,
        engineering_cost_score=candidate.priority.engineering_cost_score,
        security_risk_score=candidate.priority.security_risk_score,
        semantic_risk_score=candidate.priority.semantic_risk_score,
        evidence_quality_score=candidate.priority.evidence_quality_score,
        testability_score=candidate.priority.testability_score,
        composite_score=candidate.priority.composite_score,
    )
    demand = ObservedDemandSnapshot(
        distinct_binary_digests=candidate.demand.distinct_binary_digests,
        distinct_application_fingerprints=candidate.demand.distinct_application_fingerprints,
        blocked_session_count=candidate.demand.blocked_session_count,
        false_positive_gap_count=candidate.demand.false_positive_gap_count,
        most_recent_evidence_at=candidate.demand.most_recent_evidence_at,
    )
    impact = BoundedImpactSnapshot(
        analyses_blocker_removable=candidate.impact.analyses_blocker_removable,
        binaries_ineligible_to_eligible=candidate.impact.binaries_ineligible_to_eligible,
        behavior_coverage_increase_percent=candidate.impact.behavior_coverage_increase_percent,
        impact_summary=candidate.impact.impact_summary,
    )

    default_title = (
        f"{candidate.provider_id} / {candidate.capability_id} / {candidate.behavior_id}"
    )
    acceptance = build_acceptance_criteria_for_behavior(
        candidate.capability_id or "",
        candidate.behavior_id or "",
    )
    security_items = _security_items_from_candidate(candidate)

    prerequisites: List[str] = []
    if candidate.capability_id == "filesystem.basic_io" and candidate.behavior_id == "append_existing_file":
        prereq = _candidate_from_behavior(
            candidate.provider_id, "filesystem.basic_io", "create_always_write"
        )
        if prereq:
            prerequisites.append(
                compute_work_item_id(
                    prereq.provider_id,
                    prereq.capability_id,
                    prereq.behavior_id or "",
                )
            )

    body = {
        "work_item_id": work_item_id,
        "candidate_id": candidate_id,
        "capability_id": candidate.capability_id,
        "behavior_id": candidate.behavior_id,
    }
    return NativeRuntimeEngineeringWorkItem(
        work_item_id=work_item_id,
        title=title or default_title,
        provider_id=candidate.provider_id,
        capability_id=candidate.capability_id or "",
        behavior_id=candidate.behavior_id or "",
        bounded_scope=candidate.implementation_scope,
        architecture=candidate.architecture,
        subsystem=candidate.subsystem,
        source_expansion_candidate_id=candidate_id,
        priority_dimensions=priority,
        observed_demand=demand,
        estimated_bounded_impact=impact,
        acceptance_criteria=acceptance,
        required_fixtures=_required_fixtures(candidate),
        required_tests=_required_tests(candidate),
        required_benchmarks=[],
        security_review_items=security_items,
        prerequisite_work_item_ids=prerequisites,
        status=WorkItemStatus.PROPOSED,
        expansion_plan_version="",
        provider_version_scope=NATIVE_LAB_IMPLEMENTATION_VERSION,
        work_item_digest=digest_of(body),
    )


def _required_fixtures(candidate: RuntimeExpansionCandidate) -> List[str]:
    fixtures: List[str] = []
    for ref in candidate.evidence_references:
        if "file_append" in ref or "fixture:" in ref:
            name = ref.replace("fixture:", "")
            fixtures.append(f"tests/fixtures/native_runtime/bin/{name}")
    if not fixtures and candidate.behavior_id == "append_existing_file":
        fixtures.append("tests/fixtures/native_runtime/bin/file_append_unsupported.exe")
    return fixtures


def _required_tests(candidate: RuntimeExpansionCandidate) -> List[str]:
    if candidate.behavior_id == "append_existing_file":
        return [
            "native_engineering:filesystem.append_existing_file",
            "calibration:file_append_unsupported.exe",
        ]
    return [f"native_engineering:{candidate.capability_id}.{candidate.behavior_id}"]


def _security_items_from_candidate(candidate: RuntimeExpansionCandidate) -> List[SecurityReviewItem]:
    items: List[SecurityReviewItem] = []
    for idx, cat in enumerate(candidate.security_risk.categories):
        items.append(
            SecurityReviewItem(
                item_id=f"sec_{idx}_{cat.value}",
                category=cat.value,
                description=candidate.security_risk.explanations.get(cat.value, cat.value),
                severity=RiskSeverity.MEDIUM if candidate.security_risk.score < 0.7 else RiskSeverity.HIGH,
                addressed=False,
            )
        )
    if not items and candidate.behavior_id == "append_existing_file":
        items.append(
            SecurityReviewItem(
                item_id="sec_filesystem_escape",
                category="filesystem_escape",
                description="Append must remain within workspace-confinement boundaries.",
                severity=RiskSeverity.MEDIUM,
                addressed=False,
            )
        )
    return items
