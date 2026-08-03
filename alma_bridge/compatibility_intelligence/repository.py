"""In-memory + file-backed analysis history."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from alma_bridge.compatibility_intelligence.models import CompatibilityAnalysisResult
from alma_bridge.config import settings


class AnalysisRepository:
    """Persist compatibility analyses by binary digest."""

    def __init__(self, store_dir: Optional[Path] = None) -> None:
        self._store_dir = store_dir or (settings.data_dir / "compatibility_intelligence")
        self._memory: Dict[str, CompatibilityAnalysisResult] = {}

    def save(self, result: CompatibilityAnalysisResult) -> None:
        self._memory[result.binary_digest] = result
        self._store_dir.mkdir(parents=True, exist_ok=True)
        path = self._store_dir / f"{result.binary_digest}.json"
        path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    def get_by_digest(self, digest: str) -> Optional[CompatibilityAnalysisResult]:
        if digest in self._memory:
            return self._memory[digest]
        path = self._store_dir / f"{digest}.json"
        if path.is_file():
            result = CompatibilityAnalysisResult.model_validate_json(path.read_text(encoding="utf-8"))
            self._memory[digest] = result
            return result
        return None

    def list_recent(self, limit: int = 50) -> List[CompatibilityAnalysisResult]:
        results: List[CompatibilityAnalysisResult] = []
        if self._store_dir.is_dir():
            files = sorted(self._store_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            for path in files[:limit]:
                try:
                    result = CompatibilityAnalysisResult.model_validate_json(
                        path.read_text(encoding="utf-8")
                    )
                    results.append(result)
                    self._memory[result.binary_digest] = result
                except (json.JSONDecodeError, ValueError):
                    continue
        return results
