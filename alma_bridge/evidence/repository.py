"""Append-only bundle and timeline storage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from alma_bridge.config import settings

from alma_bridge.evidence.models import (
    BundleVersion,
    CompatibilityEvidenceBundle,
    TimelineEvent,
)


class EvidenceRepository:
    """File-backed append-only evidence store."""

    def __init__(self, store_dir: Optional[Path] = None) -> None:
        base = store_dir or (settings.data_dir / "evidence")
        self._bundles_dir = base / "bundles"
        self._timelines_dir = base / "timelines"
        self._history_dir = base / "history"
        self._index_dir = base / "index"
        self._bundle_memory: Dict[str, CompatibilityEvidenceBundle] = {}
        self._digest_index: Dict[str, str] = {}
        self._fingerprint_index: Dict[str, str] = {}

    def _ensure_dirs(self) -> None:
        self._bundles_dir.mkdir(parents=True, exist_ok=True)
        self._timelines_dir.mkdir(parents=True, exist_ok=True)
        self._history_dir.mkdir(parents=True, exist_ok=True)
        self._index_dir.mkdir(parents=True, exist_ok=True)

    def save_bundle(self, bundle: CompatibilityEvidenceBundle) -> CompatibilityEvidenceBundle:
        """Persist bundle — append new version, never overwrite prior history."""
        self._ensure_dirs()
        existing = self.get_bundle(bundle.bundle_id)
        if existing is not None:
            if existing.bundle_digest == bundle.bundle_digest:
                return existing
            history = list(existing.historical_versions)
            history.append(
                BundleVersion(
                    version=existing.version,
                    bundle_digest=existing.bundle_digest,
                    created_at=existing.updated_at,
                    event_count=0,
                )
            )
            bundle = bundle.model_copy(
                update={
                    "version": existing.version + 1,
                    "historical_versions": history,
                }
            )
        path = self._bundles_dir / f"{bundle.bundle_id}.json"
        path.write_text(bundle.model_dump_json(indent=2), encoding="utf-8")
        self._bundle_memory[bundle.bundle_id] = bundle
        self._digest_index[bundle.binary_digest] = bundle.bundle_id
        if bundle.application_fingerprint:
            self._fingerprint_index[bundle.application_fingerprint] = bundle.bundle_id
        self._index_dir.joinpath(f"digest_{bundle.binary_digest}.json").write_text(
            json.dumps({"bundle_id": bundle.bundle_id}), encoding="utf-8"
        )
        if bundle.application_fingerprint:
            self._index_dir.joinpath(
                f"fingerprint_{bundle.application_fingerprint}.json"
            ).write_text(json.dumps({"bundle_id": bundle.bundle_id}), encoding="utf-8")
        history_path = self._history_dir / f"{bundle.bundle_id}_v{bundle.version}.json"
        history_path.write_text(bundle.model_dump_json(indent=2), encoding="utf-8")
        return bundle

    def get_bundle(self, bundle_id: str) -> Optional[CompatibilityEvidenceBundle]:
        if bundle_id in self._bundle_memory:
            return self._bundle_memory[bundle_id]
        path = self._bundles_dir / f"{bundle_id}.json"
        if not path.is_file():
            return None
        bundle = CompatibilityEvidenceBundle.model_validate_json(path.read_text(encoding="utf-8"))
        self._bundle_memory[bundle_id] = bundle
        return bundle

    def get_by_binary_digest(self, binary_digest: str) -> Optional[CompatibilityEvidenceBundle]:
        if binary_digest in self._digest_index:
            return self.get_bundle(self._digest_index[binary_digest])
        index_path = self._index_dir / f"digest_{binary_digest}.json"
        if index_path.is_file():
            bundle_id = json.loads(index_path.read_text(encoding="utf-8"))["bundle_id"]
            return self.get_bundle(bundle_id)
        for path in self._bundles_dir.glob("*.json"):
            try:
                bundle = CompatibilityEvidenceBundle.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
                if bundle.binary_digest == binary_digest:
                    self._digest_index[binary_digest] = bundle.bundle_id
                    return bundle
            except (json.JSONDecodeError, ValueError):
                continue
        return None

    def get_by_fingerprint(self, fingerprint: str) -> Optional[CompatibilityEvidenceBundle]:
        if fingerprint in self._fingerprint_index:
            return self.get_bundle(self._fingerprint_index[fingerprint])
        index_path = self._index_dir / f"fingerprint_{fingerprint}.json"
        if index_path.is_file():
            bundle_id = json.loads(index_path.read_text(encoding="utf-8"))["bundle_id"]
            return self.get_bundle(bundle_id)
        for path in self._bundles_dir.glob("*.json"):
            try:
                bundle = CompatibilityEvidenceBundle.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
                if bundle.application_fingerprint == fingerprint:
                    self._fingerprint_index[fingerprint] = bundle.bundle_id
                    return bundle
            except (json.JSONDecodeError, ValueError):
                continue
        return None

    def append_timeline_event(self, bundle_id: str, event: TimelineEvent) -> None:
        """Append-only timeline — events are never modified or deleted."""
        self._ensure_dirs()
        path = self._timelines_dir / f"{bundle_id}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")

    def list_timeline_events(self, bundle_id: str) -> List[TimelineEvent]:
        path = self._timelines_dir / f"{bundle_id}.jsonl"
        if not path.is_file():
            return []
        events: List[TimelineEvent] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(TimelineEvent.model_validate_json(line))
        return events

    def list_bundle_history(self, bundle_id: str) -> List[CompatibilityEvidenceBundle]:
        versions: List[CompatibilityEvidenceBundle] = []
        for path in sorted(self._history_dir.glob(f"{bundle_id}_v*.json")):
            try:
                versions.append(
                    CompatibilityEvidenceBundle.model_validate_json(
                        path.read_text(encoding="utf-8")
                    )
                )
            except (json.JSONDecodeError, ValueError):
                continue
        return sorted(versions, key=lambda b: b.version)

    def list_all_bundle_ids(self) -> List[str]:
        if not self._bundles_dir.is_dir():
            return []
        return sorted(p.stem for p in self._bundles_dir.glob("*.json"))
