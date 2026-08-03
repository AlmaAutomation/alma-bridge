"""Work item construction and engineering card generation."""

from __future__ import annotations

from typing import List

from alma_bridge.native_lab.checklists import checklist_progress_by_category, generate_checklist
from alma_bridge.native_lab.models import (
    AcceptanceCriterionStatus,
    ChecklistCategory,
    EngineeringAcceptanceCriterion,
    EngineeringCard,
    NativeRuntimeEngineeringWorkItem,
    WorkItemStatus,
)


def build_acceptance_criteria_for_behavior(
    capability_id: str,
    behavior_id: str,
) -> List[EngineeringAcceptanceCriterion]:
    """Deterministic acceptance criteria per behavior."""
    if capability_id == "filesystem.basic_io" and behavior_id == "append_existing_file":
        return [
            EngineeringAcceptanceCriterion(
                criterion_id="ac_semantics_defined",
                description="OPEN_EXISTING + FILE_APPEND_DATA semantics documented",
                category=ChecklistCategory.DESIGN,
                critical=True,
            ),
            EngineeringAcceptanceCriterion(
                criterion_id="ac_implementation_complete",
                description="Human implementation of append behavior complete",
                category=ChecklistCategory.IMPLEMENTATION,
                critical=True,
            ),
            EngineeringAcceptanceCriterion(
                criterion_id="ac_behavior_tests_pass",
                description="Behavior suite passes for append_existing_file",
                category=ChecklistCategory.TESTING,
                critical=True,
            ),
            EngineeringAcceptanceCriterion(
                criterion_id="ac_fixture_transition",
                description="file_append_unsupported.exe passes after implementation",
                category=ChecklistCategory.TESTING,
                critical=True,
            ),
            EngineeringAcceptanceCriterion(
                criterion_id="ac_conformance_validated",
                description="WriteFile/CreateFileW profiles validated",
                category=ChecklistCategory.CONFORMANCE,
            ),
            EngineeringAcceptanceCriterion(
                criterion_id="ac_benchmark_recorded",
                description="Append benchmark evidence recorded",
                category=ChecklistCategory.PERFORMANCE,
            ),
            EngineeringAcceptanceCriterion(
                criterion_id="ac_verification_complete",
                description="VerificationEngine review completed",
                category=ChecklistCategory.VERIFICATION,
                critical=True,
                verification_related=True,
            ),
            EngineeringAcceptanceCriterion(
                criterion_id="ac_security_review",
                description="Filesystem escape security review addressed",
                category=ChecklistCategory.DESIGN,
                critical=True,
                security_related=True,
            ),
            EngineeringAcceptanceCriterion(
                criterion_id="ac_overlapped_preserved",
                description="overlapped_io remains unsupported separately",
                category=ChecklistCategory.GOVERNANCE,
                critical=True,
            ),
        ]
    return [
        EngineeringAcceptanceCriterion(
            criterion_id="ac_scope_defined",
            description="Bounded scope documented",
            category=ChecklistCategory.DESIGN,
            critical=True,
        ),
        EngineeringAcceptanceCriterion(
            criterion_id="ac_implementation_complete",
            description="Human implementation complete",
            category=ChecklistCategory.IMPLEMENTATION,
            critical=True,
        ),
        EngineeringAcceptanceCriterion(
            criterion_id="ac_tests_pass",
            description="Behavior tests pass",
            category=ChecklistCategory.TESTING,
            critical=True,
        ),
        EngineeringAcceptanceCriterion(
            criterion_id="ac_verification_complete",
            description="Verification review complete",
            category=ChecklistCategory.VERIFICATION,
            critical=True,
            verification_related=True,
        ),
    ]


def build_engineering_card(
    work_item: NativeRuntimeEngineeringWorkItem,
    *,
    current_maturity: str = "",
    current_certification_level: str = "",
    blockers: List[str] | None = None,
) -> EngineeringCard:
    """Deterministic engineering card for human review."""
    checklist = generate_checklist(work_item)
    progress = checklist_progress_by_category(checklist.items)

    demand_parts = []
    if work_item.observed_demand.distinct_binary_digests:
        demand_parts.append(
            f"{work_item.observed_demand.distinct_binary_digests} distinct binaries"
        )
    if work_item.observed_demand.blocked_session_count:
        demand_parts.append(
            f"{work_item.observed_demand.blocked_session_count} blocked sessions"
        )
    demand_summary = "; ".join(demand_parts) if demand_parts else "Observed via expansion planning"

    impact = work_item.estimated_bounded_impact.impact_summary
    if not impact:
        impact = (
            f"Removes blocker for {work_item.behavior_id} — "
            f"up to {work_item.estimated_bounded_impact.analyses_blocker_removable} analyses"
        )

    required_evidence = list(work_item.required_fixtures) + list(work_item.required_tests)
    for ref in work_item.evidence_references:
        required_evidence.append(ref.artifact_id)

    return EngineeringCard(
        work_item_id=work_item.work_item_id,
        title=work_item.title,
        bounded_scope=work_item.bounded_scope,
        provider_id=work_item.provider_id,
        capability_id=work_item.capability_id,
        behavior_id=work_item.behavior_id,
        status=work_item.status,
        demand_summary=demand_summary,
        impact_summary=impact,
        current_maturity=current_maturity,
        current_certification_level=current_certification_level,
        prerequisites=work_item.prerequisite_work_item_ids,
        required_evidence=required_evidence,
        security_review_items=work_item.security_review_items,
        checklist_progress=progress,
        blockers=blockers or [],
        evidence_stale=work_item.evidence_stale,
        owner=work_item.owner,
        reviewer=work_item.reviewer,
    )


def pending_acceptance_count(work_item: NativeRuntimeEngineeringWorkItem) -> int:
    return sum(
        1
        for c in work_item.acceptance_criteria
        if c.status in (AcceptanceCriterionStatus.PENDING, AcceptanceCriterionStatus.FAILED)
    )


def is_evidence_gated_complete(work_item: NativeRuntimeEngineeringWorkItem) -> bool:
    """True when all critical acceptance criteria are satisfied or validly waived."""
    for criterion in work_item.acceptance_criteria:
        if not criterion.critical:
            continue
        if criterion.status == AcceptanceCriterionStatus.SATISFIED:
            continue
        if criterion.status == AcceptanceCriterionStatus.WAIVED:
            if criterion.security_related or criterion.verification_related:
                if not criterion.waiver_reviewer or not criterion.waiver_reason:
                    return False
            continue
        return False
    return True
