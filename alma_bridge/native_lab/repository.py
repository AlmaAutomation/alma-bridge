"""Append-only persistence for native lab records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from alma_bridge.config import settings
from alma_bridge.native_lab.digest import digest_of
from alma_bridge.native_lab.errors import HistoryMutationError
from alma_bridge.native_lab.models import (
    EvidenceReference,
    NativeRuntimeEngineeringWorkItem,
    RiskReviewRecord,
    StatusEvent,
    WorkItemHistory,
)


class NativeLabRepository:
    """File-backed append-only store for engineering work items."""

    def __init__(self, store_dir: Optional[Path] = None) -> None:
        self._store_dir = store_dir or (settings.data_dir / "native_lab")
        self._items_dir = self._store_dir / "work_items"
        self._events_dir = self._store_dir / "status_events"
        self._evidence_dir = self._store_dir / "evidence_attachments"
        self._risk_dir = self._store_dir / "risk_reviews"
        self._memory_items: dict[str, NativeRuntimeEngineeringWorkItem] = {}
        self._memory_events: List[StatusEvent] = []
        self._memory_evidence: List[EvidenceReference] = []
        self._memory_risk: List[RiskReviewRecord] = []

    def _ensure_dirs(self) -> None:
        for d in (self._items_dir, self._events_dir, self._evidence_dir, self._risk_dir):
            d.mkdir(parents=True, exist_ok=True)

    def list_work_items(self) -> List[NativeRuntimeEngineeringWorkItem]:
        items: dict[str, NativeRuntimeEngineeringWorkItem] = dict(self._memory_items)
        if self._items_dir.is_dir():
            for path in sorted(self._items_dir.glob("*.json")):
                try:
                    item = NativeRuntimeEngineeringWorkItem.model_validate_json(
                        path.read_text(encoding="utf-8")
                    )
                except (json.JSONDecodeError, ValueError):
                    continue
                items[item.work_item_id] = item
        return sorted(items.values(), key=lambda i: i.created_at)

    def get_work_item(self, work_item_id: str) -> Optional[NativeRuntimeEngineeringWorkItem]:
        if work_item_id in self._memory_items:
            return self._memory_items[work_item_id]
        path = self._items_dir / f"{work_item_id}.json"
        if path.is_file():
            try:
                return NativeRuntimeEngineeringWorkItem.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, ValueError):
                return None
        return None

    def save_work_item(self, item: NativeRuntimeEngineeringWorkItem, *, create_only: bool = False) -> None:
        """Persist work item. create_only raises if item already exists."""
        self._ensure_dirs()
        path = self._items_dir / f"{item.work_item_id}.json"
        if create_only and path.exists():
            raise HistoryMutationError(f"Work item already exists: {item.work_item_id}")
        path.write_text(item.model_dump_json(indent=2), encoding="utf-8")
        self._memory_items[item.work_item_id] = item

    def append_status_event(self, event: StatusEvent) -> None:
        """Append status event — never overwrite."""
        self._ensure_dirs()
        dest = self._events_dir / f"{event.event_id}.json"
        if dest.exists():
            raise HistoryMutationError(f"Status event already exists: {event.event_id}")
        dest.write_text(event.model_dump_json(indent=2), encoding="utf-8")
        self._memory_events.append(event)
        self._merge_history(event)

    def list_status_events(self, work_item_id: str) -> List[StatusEvent]:
        events = [e for e in self._memory_events if e.work_item_id == work_item_id]
        if self._events_dir.is_dir():
            for path in sorted(self._events_dir.glob("*.json")):
                try:
                    event = StatusEvent.model_validate_json(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, ValueError):
                    continue
                if event.work_item_id == work_item_id and event.event_id not in {e.event_id for e in events}:
                    events.append(event)
        events.sort(key=lambda e: e.recorded_at)
        return events

    def get_history(self, work_item_id: str) -> WorkItemHistory:
        events = self.list_status_events(work_item_id)
        body = {"work_item_id": work_item_id, "event_count": len(events)}
        return WorkItemHistory(
            work_item_id=work_item_id,
            events=events,
            history_digest=digest_of(body),
        )

    def _merge_history(self, event: StatusEvent) -> None:
        pass  # Events stored individually; history assembled on read

    def append_evidence_attachment(
        self, work_item_id: str, reference: EvidenceReference
    ) -> None:
        self._ensure_dirs()
        dest = self._evidence_dir / f"{reference.reference_id}.json"
        if dest.exists():
            raise HistoryMutationError(f"Evidence reference already exists: {reference.reference_id}")
        dest.write_text(reference.model_dump_json(indent=2), encoding="utf-8")
        self._memory_evidence.append(reference)

    def list_evidence_attachments(self, work_item_id: str) -> List[EvidenceReference]:
        refs = [r for r in self._memory_evidence]
        if self._evidence_dir.is_dir():
            for path in sorted(self._evidence_dir.glob("*.json")):
                try:
                    ref = EvidenceReference.model_validate_json(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, ValueError):
                    continue
                if ref.reference_id not in {r.reference_id for r in refs}:
                    refs.append(ref)
        item = self.get_work_item(work_item_id)
        if item:
            item_refs = {r.reference_id for r in item.evidence_references}
            return [r for r in refs if r.reference_id in item_refs] + [
                r for r in item.evidence_references
            ]
        return []

    def append_risk_review(self, review: RiskReviewRecord) -> None:
        self._ensure_dirs()
        dest = self._risk_dir / f"{review.review_id}.json"
        if dest.exists():
            raise HistoryMutationError(f"Risk review already exists: {review.review_id}")
        dest.write_text(review.model_dump_json(indent=2), encoding="utf-8")
        self._memory_risk.append(review)

    def list_risk_reviews(self, work_item_id: str) -> List[RiskReviewRecord]:
        reviews = [r for r in self._memory_risk if r.work_item_id == work_item_id]
        if self._risk_dir.is_dir():
            for path in sorted(self._risk_dir.glob("*.json")):
                try:
                    review = RiskReviewRecord.model_validate_json(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, ValueError):
                    continue
                if review.work_item_id == work_item_id and review.review_id not in {r.review_id for r in reviews}:
                    reviews.append(review)
        reviews.sort(key=lambda r: r.recorded_at)
        return reviews
