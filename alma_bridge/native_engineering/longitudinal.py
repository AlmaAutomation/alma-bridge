"""Append-only longitudinal performance tracking."""

from __future__ import annotations

from typing import List

from alma_bridge.native_engineering.models import BenchmarkHistory, BenchmarkResult, LongitudinalPoint


def append_benchmark_result(
    history: BenchmarkHistory,
    result: BenchmarkResult,
) -> BenchmarkHistory:
    """Return new history with appended point (immutable append pattern)."""
    new_points = list(history.points)
    for metric in result.metrics:
        new_points.append(
            LongitudinalPoint(
                timestamp=result.recorded_at,
                benchmark_id=result.benchmark_id,
                metric_name=metric.name,
                value=metric.value,
                run_digest=result.run_digest,
            )
        )
    return BenchmarkHistory(benchmark_id=history.benchmark_id, points=new_points)


def build_history_from_results(results: List[BenchmarkResult]) -> List[BenchmarkHistory]:
    by_id: dict[str, BenchmarkHistory] = {}
    for result in results:
        hist = by_id.get(result.benchmark_id, BenchmarkHistory(benchmark_id=result.benchmark_id))
        by_id[result.benchmark_id] = append_benchmark_result(hist, result)
    return sorted(by_id.values(), key=lambda h: h.benchmark_id)


def merge_histories(existing: List[BenchmarkHistory], new_results: List[BenchmarkResult]) -> List[BenchmarkHistory]:
    merged = {h.benchmark_id: h for h in existing}
    for result in new_results:
        hist = merged.get(result.benchmark_id, BenchmarkHistory(benchmark_id=result.benchmark_id))
        merged[result.benchmark_id] = append_benchmark_result(hist, result)
    return sorted(merged.values(), key=lambda h: h.benchmark_id)
