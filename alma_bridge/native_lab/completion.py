"""Engineering completion vs workflow completion policy.

engineering_complete
    Implementation, tests, security, conformance, benchmarks, verification,
    calibration, and certification review artifacts are satisfied.

workflow_completed
    Governance disposition is resolved (approved, rejected, deferred, or
    not_required). Registry promotion is optional and separate.

Policy: ``WorkItemStatus.COMPLETED`` requires engineering_complete=True.
``governance_disposition=pending`` is allowed at completed status — human
governance review may follow engineering closure without blocking the
engineering cycle record.
"""

from __future__ import annotations

from alma_bridge.native_lab.errors import EvidenceGateError
from alma_bridge.native_lab.models import GovernanceDisposition, NativeRuntimeEngineeringWorkItem
from alma_bridge.native_lab.work_items import is_evidence_gated_complete


def is_engineering_complete(work_item: NativeRuntimeEngineeringWorkItem) -> bool:
    """True when all critical acceptance criteria are satisfied or validly waived."""
    return is_evidence_gated_complete(work_item)


def is_workflow_completed(work_item: NativeRuntimeEngineeringWorkItem) -> bool:
    """True when governance disposition no longer requires human action."""
    return work_item.governance_disposition in (
        GovernanceDisposition.APPROVED,
        GovernanceDisposition.REJECTED,
        GovernanceDisposition.DEFERRED,
        GovernanceDisposition.NOT_REQUIRED,
    )


def validate_completion_gates(work_item: NativeRuntimeEngineeringWorkItem) -> None:
    """Raise if work item cannot transition to completed."""
    if not is_engineering_complete(work_item):
        raise EvidenceGateError(
            "Completion requires all critical acceptance criteria satisfied "
            "or explicitly waived with reviewer"
        )
    if not work_item.evidence_references:
        raise EvidenceGateError("Completion requires at least one evidence attachment")
    if work_item.evidence_stale:
        raise EvidenceGateError("Completion blocked: evidence marked stale")

    from alma_bridge.native_lab.evidence_resolution import validate_required_evidence_resolves

    missing = validate_required_evidence_resolves(work_item)
    if missing:
        raise EvidenceGateError(
            f"Completion blocked: required evidence cannot resolve: {', '.join(missing)}"
        )
