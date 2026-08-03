"""Persistence for prediction snapshots and calibration records."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.compatibility_intelligence.models import (
    ACI_CALIBRATION_SCHEMA_VERSION,
    PredictionSnapshot,
)
from alma_bridge.config import settings


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class CalibrationRepository:
    """File-backed store for immutable prediction snapshots and calibration records."""

    ENGINE_VERSION = "aci_calibration_repository_v1"

    def __init__(self, store_dir: Optional[Path] = None) -> None:
        base = store_dir or (settings.data_dir / "compatibility_intelligence" / "calibration")
        self._snapshots_dir = base / "snapshots"
        self._outcomes_dir = base / "outcomes"
        self._records_dir = base / "records"
        self._snapshot_memory: Dict[str, PredictionSnapshot] = {}
        self._session_index: Dict[str, str] = {}

    def _ensure_dirs(self) -> None:
        self._snapshots_dir.mkdir(parents=True, exist_ok=True)
        self._outcomes_dir.mkdir(parents=True, exist_ok=True)
        self._records_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def build_snapshot_id(payload: dict) -> str:
        return sha256_v1(payload)

    def save_snapshot(self, snapshot: PredictionSnapshot) -> PredictionSnapshot:
        """Persist an immutable prediction snapshot. Raises if snapshot_id already exists."""
        self._ensure_dirs()
        path = self._snapshots_dir / f"{snapshot.snapshot_id}.json"
        if path.is_file():
            existing = PredictionSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
            return existing
        path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
        self._snapshot_memory[snapshot.snapshot_id] = snapshot
        if snapshot.session_id:
            self._session_index[snapshot.session_id] = snapshot.snapshot_id
            index_path = self._snapshots_dir / "by_session" / f"{snapshot.session_id}.json"
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_path.write_text(json.dumps({"snapshot_id": snapshot.snapshot_id}), encoding="utf-8")
        return snapshot

    def get_snapshot(self, snapshot_id: str) -> Optional[PredictionSnapshot]:
        if snapshot_id in self._snapshot_memory:
            return self._snapshot_memory[snapshot_id]
        path = self._snapshots_dir / f"{snapshot_id}.json"
        if path.is_file():
            snap = PredictionSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
            self._snapshot_memory[snapshot_id] = snap
            return snap
        return None

    def get_snapshot_by_session(self, session_id: str) -> Optional[PredictionSnapshot]:
        if session_id in self._session_index:
            return self.get_snapshot(self._session_index[session_id])
        index_path = self._snapshots_dir / "by_session" / f"{session_id}.json"
        if index_path.is_file():
            data = json.loads(index_path.read_text(encoding="utf-8"))
            return self.get_snapshot(str(data["snapshot_id"]))
        return None

    def list_snapshots(self, limit: int = 100) -> List[PredictionSnapshot]:
        self._ensure_dirs()
        results: List[PredictionSnapshot] = []
        files = sorted(
            self._snapshots_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for path in files[:limit]:
            if path.name.startswith("."):
                continue
            try:
                snap = PredictionSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
                results.append(snap)
                self._snapshot_memory[snap.snapshot_id] = snap
            except (json.JSONDecodeError, ValueError):
                continue
        return results

    def list_snapshots_by_analysis_digest(self, analysis_digest: str) -> List[PredictionSnapshot]:
        return [s for s in self.list_snapshots(limit=500) if s.analysis_digest == analysis_digest]

    def save_json_artifact(self, subdir: str, artifact_id: str, payload: dict) -> None:
        """Generic JSON persistence for outcomes and calibration records."""
        self._ensure_dirs()
        dir_path = self._snapshots_dir.parent / subdir
        dir_path.mkdir(parents=True, exist_ok=True)
        path = dir_path / f"{artifact_id}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def load_json_artifact(self, subdir: str, artifact_id: str) -> Optional[dict]:
        path = self._snapshots_dir.parent / subdir / f"{artifact_id}.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def list_json_artifacts(self, subdir: str, limit: int = 500) -> List[dict]:
        dir_path = self._snapshots_dir.parent / subdir
        if not dir_path.is_dir():
            return []
        results: List[dict] = []
        files = sorted(dir_path.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in files[:limit]:
            try:
                results.append(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
        return results
