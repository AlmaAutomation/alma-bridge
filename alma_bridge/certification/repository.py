"""Append-only certification record persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from alma_bridge.certification.digest import digest_of
from alma_bridge.certification.errors import HistoryMutationError
from alma_bridge.certification.models import CertificationHistory, CertificationRecord
from alma_bridge.config import settings


class CertificationRepository:
    """File-backed append-only store for certification history."""

    def __init__(self, store_dir: Optional[Path] = None) -> None:
        self._store_dir = store_dir or (settings.data_dir / "certification")
        self._history_dir = self._store_dir / "history"
        self._records_dir = self._store_dir / "records"
        self._memory_records: List[CertificationRecord] = []

    def _ensure_dirs(self) -> None:
        self._history_dir.mkdir(parents=True, exist_ok=True)
        self._records_dir.mkdir(parents=True, exist_ok=True)

    def _history_key(self, capability_id: str, behavior_id: str) -> str:
        return f"{capability_id}__{behavior_id}".replace("/", "_")

    def list_records(self) -> List[CertificationRecord]:
        seen: set[str] = set()
        records: List[CertificationRecord] = []
        for record in self._memory_records:
            if record.record_id not in seen:
                seen.add(record.record_id)
                records.append(record)
        if not self._records_dir.is_dir():
            return records
        for path in sorted(self._records_dir.glob("*.json")):
            try:
                record = CertificationRecord.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, ValueError):
                continue
            if record.record_id in seen:
                continue
            seen.add(record.record_id)
            records.append(record)
        return records

    def append_record(self, record: CertificationRecord) -> None:
        """Append certification record — never overwrite existing record_id."""
        self._ensure_dirs()
        dest = self._records_dir / f"{record.record_id}.json"
        if dest.exists():
            raise HistoryMutationError(f"Certification record already exists: {record.record_id}")
        dest.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        self._memory_records.append(record)
        self._merge_history(record)

    def get_history(self, capability_id: str, behavior_id: str) -> CertificationHistory:
        key = self._history_key(capability_id, behavior_id)
        path = self._history_dir / f"{key}.json"
        if path.is_file():
            try:
                return CertificationHistory.model_validate_json(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError):
                pass
        records = [
            r
            for r in self.list_records()
            if r.capability_id == capability_id and r.behavior_id == behavior_id
        ]
        records.sort(key=lambda r: r.recorded_at)
        body = {"capability_id": capability_id, "behavior_id": behavior_id}
        return CertificationHistory(
            capability_id=capability_id,
            behavior_id=behavior_id,
            records=records,
            history_digest=digest_of(body),
        )

    def _merge_history(self, record: CertificationRecord) -> None:
        history = self.get_history(record.capability_id, record.behavior_id)
        existing_ids = {r.record_id for r in history.records}
        if record.record_id in existing_ids:
            return
        merged = CertificationHistory(
            capability_id=record.capability_id,
            behavior_id=record.behavior_id,
            records=list(history.records) + [record],
        )
        body = {
            "capability_id": merged.capability_id,
            "behavior_id": merged.behavior_id,
            "count": len(merged.records),
        }
        merged.history_digest = digest_of(body)
        key = self._history_key(record.capability_id, record.behavior_id)
        path = self._history_dir / f"{key}.json"
        path.write_text(merged.model_dump_json(indent=2), encoding="utf-8")

    def last_record_metadata(
        self, capability_id: str, behavior_id: str
    ) -> Optional[dict]:
        history = self.get_history(capability_id, behavior_id)
        if not history.records:
            return None
        last = history.records[-1]
        return {
            "spec_digest": last.spec_digest,
            "implementation_version": "",
            "registry_version": "",
            "new_level": last.new_level,
        }
