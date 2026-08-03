"""Report persistence — read-only generation with optional cache."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from alma_bridge.config import settings

from alma_bridge.research.models import ResearchReport


class ResearchRepository:
    """Optional file-backed cache for generated reports — never mutates source evidence."""

    def __init__(self, store_dir: Optional[Path] = None) -> None:
        self._store_dir = store_dir or (settings.data_dir / "research" / "reports")
        self._memory: dict[str, ResearchReport] = {}

    def cache_key(self, report_type: str, window_label: str, provider_id: Optional[str]) -> str:
        prov = provider_id or "all"
        return f"{report_type}_{window_label}_{prov}"

    def get_cached(self, key: str) -> Optional[ResearchReport]:
        if key in self._memory:
            return self._memory[key]
        path = self._store_dir / f"{key}.json"
        if path.is_file():
            report = ResearchReport.model_validate_json(path.read_text(encoding="utf-8"))
            self._memory[key] = report
            return report
        return None

    def save_cache(self, key: str, report: ResearchReport) -> ResearchReport:
        self._store_dir.mkdir(parents=True, exist_ok=True)
        path = self._store_dir / f"{key}.json"
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        self._memory[key] = report
        return report

    def list_cached_keys(self) -> list[str]:
        if not self._store_dir.is_dir():
            return []
        return sorted(p.stem for p in self._store_dir.glob("*.json"))
