"""Persist specs, suite results, and benchmark history (append-only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from alma_bridge.config import settings
from alma_bridge.native_engineering.errors import HistoryMutationError
from alma_bridge.native_engineering.models import BenchmarkHistory, BenchmarkResult


class NativeEngineeringRepository:
    """File-backed store for benchmark history — append-only."""

    def __init__(self, store_dir: Optional[Path] = None) -> None:
        self._store_dir = store_dir or (settings.data_dir / "native_engineering")
        self._benchmarks_dir = self._store_dir / "benchmarks"
        self._history_dir = self._store_dir / "history"
        self._memory_results: List[BenchmarkResult] = []
        self._memory_history: List[BenchmarkHistory] = []

    def _ensure_dirs(self) -> None:
        self._benchmarks_dir.mkdir(parents=True, exist_ok=True)
        self._history_dir.mkdir(parents=True, exist_ok=True)

    def list_benchmark_results(self) -> List[BenchmarkResult]:
        results = list(self._memory_results)
        if not self._benchmarks_dir.is_dir():
            return results
        for path in sorted(self._benchmarks_dir.glob("*.json")):
            try:
                results.append(BenchmarkResult.model_validate_json(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, ValueError):
                continue
        return results

    def save_benchmark_result(self, result: BenchmarkResult) -> None:
        """Append benchmark result — never overwrite existing run_digest."""
        self._ensure_dirs()
        dest = self._benchmarks_dir / f"{result.run_digest}.json"
        if dest.exists():
            raise HistoryMutationError(f"Benchmark result already recorded: {result.run_digest}")
        dest.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        self._memory_results.append(result)

    def list_benchmark_history(self) -> List[BenchmarkHistory]:
        history = list(self._memory_history)
        if not self._history_dir.is_dir():
            return history
        for path in sorted(self._history_dir.glob("*.json")):
            try:
                history.append(BenchmarkHistory.model_validate_json(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, ValueError):
                continue
        return history

    def save_benchmark_history(self, history: BenchmarkHistory) -> None:
        """Persist merged history snapshot (append-only file per benchmark_id)."""
        self._ensure_dirs()
        path = self._history_dir / f"{history.benchmark_id}.json"
        if path.exists():
            existing = BenchmarkHistory.model_validate_json(path.read_text(encoding="utf-8"))
            existing_digests = {p.run_digest for p in existing.points}
            new_points = [p for p in history.points if p.run_digest not in existing_digests]
            if not new_points:
                return
            merged = BenchmarkHistory(
                benchmark_id=history.benchmark_id,
                points=list(existing.points) + new_points,
            )
            history = merged
        path.write_text(history.model_dump_json(indent=2), encoding="utf-8")
        self._memory_history = [h for h in self._memory_history if h.benchmark_id != history.benchmark_id]
        self._memory_history.append(history)
