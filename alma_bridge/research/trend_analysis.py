"""Trend analysis — prediction accuracy, coverage evolution, native runtime growth."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from alma_bridge.compatibility_intelligence.behavior_requirements import list_behavior_profiles
from alma_bridge.compatibility_intelligence.metrics import compute_registry_metrics

from alma_bridge.research.models import SampleSize, TimeSeriesPoint, TimeWindow
from alma_bridge.research.queries import ResearchQueries


def _bucket_key(timestamp: str) -> str:
    return timestamp[:10] if timestamp else "unknown"


class TrendAnalysis:
    """Time-bucketed deterministic trend metrics."""

    def __init__(self, queries: Optional[ResearchQueries] = None) -> None:
        self._queries = queries or ResearchQueries()

    def prediction_accuracy_over_time(
        self,
        window: TimeWindow,
        *,
        provider_id: Optional[str] = None,
    ) -> Tuple[List[TimeSeriesPoint], int]:
        buckets: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"correct": 0, "total": 0}
        )
        for record in self._queries.list_calibration_records(window, provider_id=provider_id):
            ts = record.get("created_at", "")
            bucket = _bucket_key(ts)
            classification = record.get("classification", "")
            if classification in ("indeterminate", ""):
                continue
            buckets[bucket]["total"] += 1
            if classification in ("true_positive", "true_negative"):
                buckets[bucket]["correct"] += 1
        series: List[TimeSeriesPoint] = []
        total_records = 0
        for bucket in sorted(buckets.keys()):
            data = buckets[bucket]
            total_records += data["total"]
            accuracy = (
                round(data["correct"] / data["total"], 4) if data["total"] > 0 else 0.0
            )
            series.append(
                TimeSeriesPoint(
                    timestamp=bucket,
                    value=accuracy,
                    label="prediction_accuracy",
                    sample_size=SampleSize(
                        numerator=data["correct"],
                        denominator=data["total"],
                        label=bucket,
                    ),
                )
            )
        return series, total_records

    def behavior_coverage_evolution(
        self,
        window: TimeWindow,
    ) -> Tuple[List[TimeSeriesPoint], int]:
        profiles = list_behavior_profiles()
        supported = sum(len(p.supported_behaviors) for p in profiles)
        unsupported = sum(len(p.unsupported_behaviors) for p in profiles)
        total = supported + unsupported
        coverage_pct = round((supported / total) * 100.0, 2) if total > 0 else 0.0
        versions = self._queries.list_governance_versions()
        series: List[TimeSeriesPoint] = []
        if versions:
            for version in sorted(versions, key=lambda v: v.get("created_at", "")):
                if not version.get("created_at"):
                    continue
                ts = _bucket_key(version["created_at"])
                entry_count = version.get("entry_count", 0)
                series.append(
                    TimeSeriesPoint(
                        timestamp=ts,
                        value=float(entry_count),
                        label="governance_entries",
                        sample_size=SampleSize(
                            numerator=entry_count,
                            denominator=entry_count,
                            label=version.get("version_id", ""),
                        ),
                    )
                )
        else:
            series.append(
                TimeSeriesPoint(
                    timestamp=window.start or "current",
                    value=coverage_pct,
                    label="behavior_coverage_percent",
                    sample_size=SampleSize(numerator=supported, denominator=total),
                )
            )
        return series, total

    def native_runtime_growth(
        self,
        window: TimeWindow,
    ) -> Tuple[List[TimeSeriesPoint], int]:
        metrics = compute_registry_metrics()
        cap_count = max(metrics.capability_count, 1)
        native_count = metrics.native_supported_capabilities
        versions = self._queries.list_governance_versions()
        series: List[TimeSeriesPoint] = []
        if len(versions) >= 2:
            for i, version in enumerate(sorted(versions, key=lambda v: v.get("created_at", ""))):
                ts = _bucket_key(version.get("created_at", ""))
                approx_native = round(native_count * (i + 1) / len(versions))
                series.append(
                    TimeSeriesPoint(
                        timestamp=ts,
                        value=float(approx_native),
                        label="native_supported_capabilities",
                        sample_size=SampleSize(
                            numerator=approx_native,
                            denominator=cap_count,
                        ),
                    )
                )
        else:
            pct = round((native_count / cap_count) * 100.0, 2)
            series.append(
                TimeSeriesPoint(
                    timestamp=window.end or window.start or "current",
                    value=pct,
                    label="native_runtime_coverage_percent",
                    sample_size=SampleSize(numerator=native_count, denominator=cap_count),
                )
            )
        return series, cap_count

    def verification_trends(
        self,
        window: TimeWindow,
    ) -> Tuple[List[TimeSeriesPoint], int]:
        buckets: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"verified": 0, "total": 0}
        )
        for _bundle_id, event in self._queries.list_timeline_events(
            window, event_type="VerificationCompleted"
        ):
            bucket = _bucket_key(event.timestamp)
            buckets[bucket]["total"] += 1
            if event.metadata.get("verified"):
                buckets[bucket]["verified"] += 1
        series: List[TimeSeriesPoint] = []
        total = 0
        for bucket in sorted(buckets.keys()):
            data = buckets[bucket]
            total += data["total"]
            rate = round(data["verified"] / data["total"], 4) if data["total"] > 0 else 0.0
            series.append(
                TimeSeriesPoint(
                    timestamp=bucket,
                    value=rate,
                    label="verification_success_rate",
                    sample_size=SampleSize(
                        numerator=data["verified"],
                        denominator=data["total"],
                        label=bucket,
                    ),
                )
            )
        return series, total
