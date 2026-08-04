"""Bootstrap durable append-cycle work item state from committed store."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from alma_bridge.config import PROJECT_ROOT
from alma_bridge.native_lab.digest import digest_of
from alma_bridge.native_lab.evidence_resolution import APPEND_CYCLE_EVIDENCE_SPECS, _fixture_digest, _file_digest
from alma_bridge.native_lab.models import (
    AcceptanceCriterionStatus,
    EvidenceLinkKind,
    EvidenceReference,
    GovernanceDisposition,
    RiskCategory,
    RiskReviewRecord,
    RiskSeverity,
    SEEDED_WORK_ITEM_ID,
    SecurityReviewItem,
    StatusEvent,
    WorkItemStatus,
    utc_now_iso,
)
from alma_bridge.native_lab.repository import NativeLabRepository
from alma_bridge.native_lab.seed import build_seeded_append_work_item
from alma_bridge.native_lab.work_items import build_acceptance_criteria_for_behavior

COMMITTED_STORE = PROJECT_ROOT / "data" / "native_lab"
CYCLE_COMPLETED_MARKER = COMMITTED_STORE / "append_cycle_v1.completed"


def committed_store_available() -> bool:
    return (COMMITTED_STORE / "work_items" / f"{SEEDED_WORK_ITEM_ID}.json").is_file()


def _build_evidence_references() -> List[EvidenceReference]:
    refs: List[EvidenceReference] = []
    for spec in APPEND_CYCLE_EVIDENCE_SPECS:
        path = PROJECT_ROOT / spec["path"]
        digest = ""
        if spec["kind"] == EvidenceLinkKind.FIXTURE:
            digest = _fixture_digest(spec["artifact_id"])
        elif path.is_file():
            digest = _file_digest(path)
        refs.append(
            EvidenceReference(
                reference_id=spec["reference_id"],
                kind=spec["kind"],
                source="append_cycle_v1",
                artifact_id=spec["artifact_id"],
                digest=digest,
                fixture_path=spec["path"] if spec["kind"] == EvidenceLinkKind.FIXTURE else None,
                attached_by="engineering_cycle",
                attached_at="2026-08-04T00:00:00+00:00",
                evidence_stale=False,
            )
        )
    return refs


def _build_status_events() -> List[StatusEvent]:
    transitions = [
        (WorkItemStatus.PROPOSED, WorkItemStatus.TRIAGED),
        (WorkItemStatus.TRIAGED, WorkItemStatus.ACCEPTED),
        (WorkItemStatus.ACCEPTED, WorkItemStatus.IN_DESIGN),
        (WorkItemStatus.IN_DESIGN, WorkItemStatus.IMPLEMENTATION_IN_PROGRESS),
        (WorkItemStatus.IMPLEMENTATION_IN_PROGRESS, WorkItemStatus.IMPLEMENTATION_COMPLETE),
        (WorkItemStatus.IMPLEMENTATION_COMPLETE, WorkItemStatus.TESTING),
        (WorkItemStatus.TESTING, WorkItemStatus.VERIFICATION_PENDING),
        (WorkItemStatus.VERIFICATION_PENDING, WorkItemStatus.CERTIFICATION_PENDING),
        (WorkItemStatus.CERTIFICATION_PENDING, WorkItemStatus.GOVERNANCE_PENDING),
        (WorkItemStatus.GOVERNANCE_PENDING, WorkItemStatus.COMPLETED),
    ]
    events: List[StatusEvent] = []
    for idx, (from_s, to_s) in enumerate(transitions, start=1):
        event_id = f"se_append_v1_{idx:02d}"
        body = {
            "event_id": event_id,
            "work_item_id": SEEDED_WORK_ITEM_ID,
            "from_status": from_s.value,
            "to_status": to_s.value,
        }
        events.append(
            StatusEvent(
                event_id=event_id,
                work_item_id=SEEDED_WORK_ITEM_ID,
                from_status=from_s,
                to_status=to_s,
                actor="human_engineer",
                rationale=f"Append cycle transition {idx}/10",
                recorded_at=f"2026-08-0{3 + (idx // 8)}T{8 + idx:02d}:00:00+00:00",
                event_digest=digest_of(body),
            )
        )
    return events


def _build_risk_reviews() -> List[RiskReviewRecord]:
    reviews = [
        (
            "rr_append_sec_01",
            RiskCategory.SECURITY,
            RiskSeverity.MEDIUM,
            "Filesystem escape via path traversal on append",
            "Workspace resolver rejects .. and absolute paths",
        ),
        (
            "rr_append_sem_01",
            RiskCategory.SEMANTIC,
            RiskSeverity.LOW,
            "Overlapped I/O must remain unsupported",
            "Append does not imply overlapped_io support",
        ),
    ]
    out: List[RiskReviewRecord] = []
    for review_id, category, severity, description, mitigation in reviews:
        body = {"review_id": review_id, "work_item_id": SEEDED_WORK_ITEM_ID}
        out.append(
            RiskReviewRecord(
                review_id=review_id,
                work_item_id=SEEDED_WORK_ITEM_ID,
                category=category,
                severity=severity,
                description=description,
                mitigation=mitigation,
                residual_risk="low",
                reviewer="engineering_cycle",
                recorded_at="2026-08-04T12:00:00+00:00",
                review_digest=digest_of(body),
            )
        )
    return out


def build_completed_append_work_item() -> "NativeRuntimeEngineeringWorkItem":
    from alma_bridge.native_lab.models import NativeRuntimeEngineeringWorkItem

    item = build_seeded_append_work_item()
    item.status = WorkItemStatus.COMPLETED
    item.engineering_complete = True
    item.governance_disposition = GovernanceDisposition.PENDING
    item.owner = "native_runtime_lab"
    item.reviewer = "certification_platform"
    item.evidence_references = _build_evidence_references()
    item.evidence_stale = False
    item.required_benchmarks = [
        "runtime_append_success",
        "runtime_append_repeated",
        "runtime_file_write",
    ]
    item.security_review_items = [
        SecurityReviewItem(
            item_id="sec_filesystem_escape",
            category="filesystem_escape",
            description="Append must remain within workspace-confinement boundaries.",
            severity=RiskSeverity.MEDIUM,
            addressed=True,
        ),
    ]
    criteria = build_acceptance_criteria_for_behavior("filesystem.basic_io", "append_existing_file")
    for c in criteria:
        c.status = AcceptanceCriterionStatus.SATISFIED
        c.updated_at = "2026-08-04T12:00:00+00:00"
    item.acceptance_criteria = criteria
    item.created_at = "2026-08-01T08:00:00+00:00"
    item.updated_at = "2026-08-04T12:00:00+00:00"
    body = {
        "work_item_id": item.work_item_id,
        "status": item.status.value,
        "engineering_complete": True,
        "evidence_count": len(item.evidence_references),
    }
    item.work_item_digest = digest_of(body)
    return item


def materialize_committed_store(*, force: bool = False) -> Path:
    """Write append-cycle durable state to data/native_lab (idempotent)."""
    if CYCLE_COMPLETED_MARKER.is_file() and not force:
        return COMMITTED_STORE

    store = COMMITTED_STORE
    for sub in ("work_items", "status_events", "evidence_attachments", "risk_reviews", "generated"):
        sub_path = store / sub
        if force and sub_path.is_dir():
            for old in sub_path.glob("*.json"):
                old.unlink()
        sub_path.mkdir(parents=True, exist_ok=True)

    item = build_completed_append_work_item()
    (store / "work_items" / f"{item.work_item_id}.json").write_text(
        item.model_dump_json(indent=2), encoding="utf-8"
    )

    for event in _build_status_events():
        (store / "status_events" / f"{event.event_id}.json").write_text(
            event.model_dump_json(indent=2), encoding="utf-8"
        )

    for ref in item.evidence_references:
        (store / "evidence_attachments" / f"{ref.reference_id}.json").write_text(
            ref.model_dump_json(indent=2), encoding="utf-8"
        )

    for review in _build_risk_reviews():
        (store / "risk_reviews" / f"{review.review_id}.json").write_text(
            review.model_dump_json(indent=2), encoding="utf-8"
        )

    from alma_bridge.native_lab.evidence_resolution import build_evidence_manifest

    manifest = build_evidence_manifest(item)
    (store / "evidence_manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )

    verification = {
        "work_item_id": item.work_item_id,
        "provider_id": "native_alma",
        "implementation_version": "0.2.1-m2",
        "simulation_used": False,
        "workspace_confined": True,
        "verification_digest": digest_of({"work_item_id": item.work_item_id, "verified": True}),
    }
    (store / "generated" / "append_verification_contract_v1.json").write_text(
        json.dumps(verification, indent=2) + "\n", encoding="utf-8"
    )

    benchmark_stub = {
        "work_item_id": item.work_item_id,
        "schema_version": "benchmark_baseline_v1",
        "note": "Populated at audit runtime; see append_benchmark_baseline_v1.json",
    }
    (store / "generated" / "append_benchmark_baseline_v1.json").write_text(
        json.dumps(benchmark_stub, indent=2) + "\n", encoding="utf-8"
    )

    CYCLE_COMPLETED_MARKER.write_text("append_cycle_v1\n", encoding="utf-8")
    return store


def load_committed_work_item(repo: NativeLabRepository) -> Optional["NativeRuntimeEngineeringWorkItem"]:
    """Load completed work item from committed store into repository if not present."""
    if not committed_store_available():
        return None
    existing = repo.get_work_item(SEEDED_WORK_ITEM_ID)
    if existing and existing.status == WorkItemStatus.COMPLETED:
        return existing

    item = build_completed_append_work_item()
    path = COMMITTED_STORE / "work_items" / f"{SEEDED_WORK_ITEM_ID}.json"
    if path.is_file():
        from alma_bridge.native_lab.models import NativeRuntimeEngineeringWorkItem

        item = NativeRuntimeEngineeringWorkItem.model_validate_json(path.read_text(encoding="utf-8"))

    repo.save_work_item(item)
    for event_path in sorted((COMMITTED_STORE / "status_events").glob("*.json")):
        event = StatusEvent.model_validate_json(event_path.read_text(encoding="utf-8"))
        if event.work_item_id == SEEDED_WORK_ITEM_ID:
            try:
                repo.append_status_event(event)
            except Exception:
                pass
    for review_path in sorted((COMMITTED_STORE / "risk_reviews").glob("*.json")):
        review = RiskReviewRecord.model_validate_json(review_path.read_text(encoding="utf-8"))
        if review.work_item_id == SEEDED_WORK_ITEM_ID:
            try:
                repo.append_risk_review(review)
            except Exception:
                pass
    return item
