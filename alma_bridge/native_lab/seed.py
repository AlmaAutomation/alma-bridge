"""Seed initial engineering work items."""

from __future__ import annotations

from alma_bridge.compatibility_intelligence.expansion.service import ExpansionPlanningService
from alma_bridge.native_lab.candidates import create_work_item_from_candidate
from alma_bridge.native_lab.models import (
    EvidenceLinkKind,
    EvidenceReference,
    NATIVE_LAB_IMPLEMENTATION_VERSION,
    SEEDED_WORK_ITEM_ID,
    NativeRuntimeEngineeringWorkItem,
    WorkItemStatus,
)
from alma_bridge.native_lab.repository import NativeLabRepository


def _find_append_candidate_id() -> str:
    service = ExpansionPlanningService()
    plan = service.generate_plan()
    for candidate in plan.ranked_candidates:
        if (
            candidate.capability_id == "filesystem.basic_io"
            and candidate.behavior_id == "append_existing_file"
        ):
            return candidate.candidate_id
    return "expansion_filesystem.basic_io_append_existing_file"


def build_seeded_append_work_item() -> NativeRuntimeEngineeringWorkItem:
    """Fully scoped engineering card for append_existing_file — does not implement behavior."""
    candidate_id = _find_append_candidate_id()
    item = create_work_item_from_candidate(
        candidate_id,
        title="PE64 console synchronous workspace-confined append (append_existing_file)",
    )
    item.work_item_id = SEEDED_WORK_ITEM_ID
    item.status = WorkItemStatus.PROPOSED
    item.owner = ""
    item.reviewer = ""
    item.provider_version_scope = NATIVE_LAB_IMPLEMENTATION_VERSION
    item.evidence_references = [
        EvidenceReference(
            reference_id="ev_file_append_unsupported",
            kind=EvidenceLinkKind.FIXTURE,
            source="native_runtime_fixtures",
            artifact_id="file_append_unsupported.exe",
            digest="d4cead243e918d4f5cc4d1c3220ff17d6d2c97a2491db5ba105c05bd5d119a3a",
            fixture_path="tests/fixtures/native_runtime/bin/file_append_unsupported.exe",
        ),
        EvidenceReference(
            reference_id="ev_aci_gap",
            kind=EvidenceLinkKind.ANALYSIS,
            source="aci_calibration",
            artifact_id="file_append_unsupported.exe_calibration",
            digest="",
        ),
        EvidenceReference(
            reference_id="ev_expansion_candidate",
            kind=EvidenceLinkKind.EXPANSION,
            source="aci_expansion",
            artifact_id=candidate_id,
        ),
        EvidenceReference(
            reference_id="ev_certification_unsupported",
            kind=EvidenceLinkKind.CERTIFICATION,
            source="certification_platform",
            artifact_id="filesystem.basic_io/append_existing_file",
        ),
        EvidenceReference(
            reference_id="ev_createfilew_profile",
            kind=EvidenceLinkKind.SPECIFICATION,
            source="native_engineering",
            artifact_id="kernel32.dll!CreateFileW",
        ),
        EvidenceReference(
            reference_id="ev_writefile_profile",
            kind=EvidenceLinkKind.SPECIFICATION,
            source="native_engineering",
            artifact_id="kernel32.dll!WriteFile",
        ),
    ]
    return item


def ensure_seeded_work_item(repo: NativeLabRepository) -> NativeRuntimeEngineeringWorkItem:
    """Idempotent seed — returns existing or creates seeded item."""
    existing = repo.get_work_item(SEEDED_WORK_ITEM_ID)
    if existing:
        return existing
    item = build_seeded_append_work_item()
    repo.save_work_item(item, create_only=True)
    return item
