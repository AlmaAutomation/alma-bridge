"""Deterministic checklist generation for engineering work items."""

from __future__ import annotations

from typing import Dict, List, Tuple

from alma_bridge.native_lab.digest import digest_of
from alma_bridge.native_lab.models import (
    ChecklistCategory,
    ChecklistEvaluation,
    ChecklistItem,
    ChecklistItemStatus,
    NativeRuntimeEngineeringWorkItem,
)

# Canonical checklist templates keyed by (capability_id, behavior_id).
# Items 1-14 for append_existing_file span Design through Governance.
BEHAVIOR_CHECKLIST_TEMPLATES: Dict[Tuple[str, str], List[dict]] = {
    ("filesystem.basic_io", "append_existing_file"): [
        {
            "item_id": "cl_01_define_semantics",
            "category": ChecklistCategory.DESIGN,
            "ordinal": 1,
            "title": "Define OPEN_EXISTING + FILE_APPEND_DATA semantics",
            "description": "Document expected CreateFileW/WriteFile behavior for append to existing file.",
        },
        {
            "item_id": "cl_02_document_access_modes",
            "category": ChecklistCategory.DESIGN,
            "ordinal": 2,
            "title": "Document CreateFileW access mode requirements",
            "description": "Specify FILE_APPEND_DATA and related access flags.",
        },
        {
            "item_id": "cl_03_specify_writefile_append",
            "category": ChecklistCategory.DESIGN,
            "ordinal": 3,
            "title": "Specify WriteFile append semantics",
            "description": "Define pointer advancement, partial writes, and error modes.",
        },
        {
            "item_id": "cl_04_handle_lifecycle",
            "category": ChecklistCategory.DESIGN,
            "ordinal": 4,
            "title": "Identify handle lifecycle requirements",
            "description": "CloseHandle, invalid handle, and double-close behavior.",
        },
        {
            "item_id": "cl_05_workspace_confinement",
            "category": ChecklistCategory.DESIGN,
            "ordinal": 5,
            "title": "Confirm workspace-confinement boundaries",
            "description": "Append operations must remain within sandbox workspace.",
        },
        {
            "item_id": "cl_06_implement_createfilew",
            "category": ChecklistCategory.IMPLEMENTATION,
            "ordinal": 6,
            "title": "Human implementation: CreateFileW OPEN_EXISTING path",
            "description": "Engineer implements OPEN_EXISTING without CREATE_ALWAYS.",
        },
        {
            "item_id": "cl_07_implement_append_data",
            "category": ChecklistCategory.IMPLEMENTATION,
            "ordinal": 7,
            "title": "Human implementation: FILE_APPEND_DATA access mode",
            "description": "Engineer implements FILE_APPEND_DATA flag handling.",
        },
        {
            "item_id": "cl_08_implement_writefile_append",
            "category": ChecklistCategory.IMPLEMENTATION,
            "ordinal": 8,
            "title": "Human implementation: WriteFile append behavior",
            "description": "Engineer implements append-at-EOF WriteFile semantics.",
        },
        {
            "item_id": "cl_09_add_behavior_suite",
            "category": ChecklistCategory.TESTING,
            "ordinal": 9,
            "title": "Add behavior suite cases for append_existing_file",
            "description": "Extend native engineering behavior suite with append scenarios.",
        },
        {
            "item_id": "cl_10_verify_fixture_transition",
            "category": ChecklistCategory.TESTING,
            "ordinal": 10,
            "title": "Verify file_append_unsupported.exe outcome after implementation",
            "description": "Negative fixture should transition to pass when behavior is implemented.",
        },
        {
            "item_id": "cl_11_validate_api_profiles",
            "category": ChecklistCategory.CONFORMANCE,
            "ordinal": 11,
            "title": "Validate against WriteFile/CreateFileW engineering profiles",
            "description": "Conformance check against native engineering API profiles.",
        },
        {
            "item_id": "cl_12_benchmark_append",
            "category": ChecklistCategory.PERFORMANCE,
            "ordinal": 12,
            "title": "Benchmark append throughput within tolerance",
            "description": "Record benchmark evidence for append I/O performance.",
        },
        {
            "item_id": "cl_13_request_verification",
            "category": ChecklistCategory.VERIFICATION,
            "ordinal": 13,
            "title": "Request VerificationEngine review with evidence",
            "description": "Submit verification request with attached test evidence.",
        },
        {
            "item_id": "cl_14_preserve_overlapped_unsupported",
            "category": ChecklistCategory.GOVERNANCE,
            "ordinal": 14,
            "title": "Preserve overlapped_io unsupported separately",
            "description": "Do not conflate append support with overlapped I/O; keep distinct.",
        },
    ],
}

DEFAULT_CHECKLIST_TEMPLATE: List[dict] = [
    {
        "item_id": "cl_default_01_scope",
        "category": ChecklistCategory.DESIGN,
        "ordinal": 1,
        "title": "Define bounded implementation scope",
        "description": "Document semantics and boundaries for the behavior.",
    },
    {
        "item_id": "cl_default_02_implement",
        "category": ChecklistCategory.IMPLEMENTATION,
        "ordinal": 2,
        "title": "Human implementation milestone",
        "description": "Track human implementation progress.",
    },
    {
        "item_id": "cl_default_03_test",
        "category": ChecklistCategory.TESTING,
        "ordinal": 3,
        "title": "Add behavior test evidence",
        "description": "Attach behavior suite and fixture evidence.",
    },
    {
        "item_id": "cl_default_04_conformance",
        "category": ChecklistCategory.CONFORMANCE,
        "ordinal": 4,
        "title": "Validate API conformance",
        "description": "Check against engineering profiles.",
    },
    {
        "item_id": "cl_default_05_verify",
        "category": ChecklistCategory.VERIFICATION,
        "ordinal": 5,
        "title": "Request verification review",
        "description": "Submit for VerificationEngine review.",
    },
    {
        "item_id": "cl_default_06_certify",
        "category": ChecklistCategory.CERTIFICATION,
        "ordinal": 6,
        "title": "Request certification review",
        "description": "Submit for certification platform review.",
    },
    {
        "item_id": "cl_default_07_govern",
        "category": ChecklistCategory.GOVERNANCE,
        "ordinal": 7,
        "title": "Governance review",
        "description": "Confirm registry and scope preservation.",
    },
]


def generate_checklist(work_item: NativeRuntimeEngineeringWorkItem) -> ChecklistEvaluation:
    """Deterministic checklist for a work item."""
    key = (work_item.capability_id, work_item.behavior_id)
    template = BEHAVIOR_CHECKLIST_TEMPLATES.get(key, DEFAULT_CHECKLIST_TEMPLATE)
    items = [
        ChecklistItem(
            item_id=t["item_id"],
            category=t["category"],
            ordinal=t["ordinal"],
            title=t["title"],
            description=t.get("description", ""),
            status=ChecklistItemStatus.PENDING,
            required=True,
        )
        for t in template
    ]
    categories = sorted({c.value for c in ChecklistCategory})
    satisfied = sum(1 for i in items if i.status == ChecklistItemStatus.SATISFIED)
    progress = (satisfied / len(items) * 100.0) if items else 0.0
    body = {
        "work_item_id": work_item.work_item_id,
        "item_count": len(items),
        "capability_id": work_item.capability_id,
        "behavior_id": work_item.behavior_id,
    }
    return ChecklistEvaluation(
        work_item_id=work_item.work_item_id,
        items=items,
        categories=categories,
        progress_pct=round(progress, 1),
        evaluation_digest=digest_of(body),
    )


def checklist_progress_by_category(items: List[ChecklistItem]) -> Dict[str, int]:
    """Count satisfied items per category."""
    progress: Dict[str, int] = {}
    for item in items:
        cat = item.category.value
        if cat not in progress:
            progress[cat] = 0
        if item.status == ChecklistItemStatus.SATISFIED:
            progress[cat] += 1
    return progress
