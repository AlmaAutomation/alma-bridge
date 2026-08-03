"""Workflow metrics dashboard with sample sizes."""

from __future__ import annotations

from alma_bridge.native_lab.models import NativeLabDashboard, WorkItemStatus
from alma_bridge.native_lab.queries import NativeLabQueries


BACKLOG_STATUSES = {WorkItemStatus.PROPOSED, WorkItemStatus.TRIAGED}
ACTIVE_STATUSES = {
    WorkItemStatus.ACCEPTED,
    WorkItemStatus.IN_DESIGN,
    WorkItemStatus.IMPLEMENTATION_IN_PROGRESS,
    WorkItemStatus.IMPLEMENTATION_COMPLETE,
    WorkItemStatus.TESTING,
}


def build_native_lab_dashboard(queries: NativeLabQueries) -> NativeLabDashboard:
    items = queries.list_work_items()
    by_status: dict[str, int] = {}
    for item in items:
        key = item.status.value
        by_status[key] = by_status.get(key, 0) + 1

    stale_count = sum(1 for i in items if i.evidence_stale)
    limitations = [
        "Dashboard counts reflect persisted work items only.",
        "Laboratory does not execute binaries or modify runtime source.",
    ]
    return NativeLabDashboard(
        total_work_items=len(items),
        by_status=by_status,
        backlog_count=sum(1 for i in items if i.status in BACKLOG_STATUSES),
        active_count=sum(1 for i in items if i.status in ACTIVE_STATUSES),
        verification_queue_count=sum(
            1 for i in items if i.status == WorkItemStatus.VERIFICATION_PENDING
        ),
        certification_queue_count=sum(
            1 for i in items if i.status == WorkItemStatus.CERTIFICATION_PENDING
        ),
        completed_count=sum(1 for i in items if i.status == WorkItemStatus.COMPLETED),
        blocked_count=sum(1 for i in items if i.status == WorkItemStatus.BLOCKED),
        stale_evidence_count=stale_count,
        sample_sizes={
            "work_items": len(items),
            "with_evidence": sum(1 for i in items if i.evidence_references),
            "with_prerequisites": sum(1 for i in items if i.prerequisite_work_item_ids),
        },
        limitations=limitations,
    )
