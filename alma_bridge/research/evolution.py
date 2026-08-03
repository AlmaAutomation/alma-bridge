"""Capability maturity and governance velocity evolution metrics."""

from __future__ import annotations

from collections import Counter
from typing import List, Optional, Tuple

from alma_bridge.research.models import SampleSize, TimeSeriesPoint, TimeWindow
from alma_bridge.research.queries import ResearchQueries


def _bucket_key(timestamp: str) -> str:
    return timestamp[:10] if timestamp else "unknown"


class EvolutionAnalytics:
    """Governance and maturity evolution — read-only registry history."""

    def __init__(self, queries: Optional[ResearchQueries] = None) -> None:
        self._queries = queries or ResearchQueries()

    def capability_maturity_growth(
        self,
        window: TimeWindow,
    ) -> Tuple[List[TimeSeriesPoint], int]:
        versions = self._queries.list_governance_versions()
        series: List[TimeSeriesPoint] = []
        total_entries = 0
        for version in sorted(versions, key=lambda v: v.get("created_at", "")):
            ts = version.get("created_at", "")
            if ts and window.start and ts < window.start:
                continue
            if ts and window.end and ts > window.end:
                continue
            entry_count = version.get("entry_count", 0)
            total_entries = max(total_entries, entry_count)
            series.append(
                TimeSeriesPoint(
                    timestamp=_bucket_key(ts),
                    value=float(entry_count),
                    label="registry_entries",
                    sample_size=SampleSize(
                        numerator=entry_count,
                        denominator=entry_count,
                        label=version.get("version_id", ""),
                    ),
                )
            )
        if not series:
            from alma_bridge.research.analytics import EvidenceAnalytics

            counts, total = EvidenceAnalytics(self._queries).capability_maturity_counts()
            stable = counts.get("stable", 0) + counts.get("verified_bounded", 0)
            series.append(
                TimeSeriesPoint(
                    timestamp="current",
                    value=float(stable),
                    label="stable_capabilities",
                    sample_size=SampleSize(numerator=stable, denominator=max(total, 1)),
                )
            )
            total_entries = total
        return series, total_entries

    def governance_velocity(
        self,
        window: TimeWindow,
    ) -> Tuple[List[TimeSeriesPoint], int]:
        proposals = self._queries.list_governance_proposals()
        buckets: Counter[str] = Counter()
        status_counts: Counter[str] = Counter()
        for proposal in proposals:
            ts = proposal.get("created_at") or proposal.get("updated_at", "")
            if ts and not _in_window_simple(ts, window):
                continue
            buckets[_bucket_key(ts)] += 1
            status_counts[proposal.get("status", "unknown")] += 1
        series: List[TimeSeriesPoint] = []
        total = sum(buckets.values())
        for bucket in sorted(buckets.keys()):
            count = buckets[bucket]
            series.append(
                TimeSeriesPoint(
                    timestamp=bucket,
                    value=float(count),
                    label="governance_proposals",
                    sample_size=SampleSize(numerator=count, denominator=total or count),
                )
            )
        return series, total

    def expansion_completion(
        self,
        window: TimeWindow,
    ) -> Tuple[int, int, int]:
        plan = self._queries.get_expansion_plan()
        if plan is None:
            return 0, 0, 0
        total = len(plan.candidates)
        return total, 0, total


def _in_window_simple(ts: str, window: TimeWindow) -> bool:
    if window.label == "all_time":
        return True
    if window.start and ts < window.start:
        return False
    if window.end and ts > window.end:
        return False
    return True
