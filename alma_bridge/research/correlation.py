"""Descriptive capability/blocker correlations — not causal inference."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

from alma_bridge.research.models import SampleSize, TimeWindow
from alma_bridge.research.queries import ResearchQueries


class CorrelationAnalytics:
    """Observed co-occurrence statistics between capabilities and blockers."""

    def __init__(self, queries: Optional[ResearchQueries] = None) -> None:
        self._queries = queries or ResearchQueries()

    def capability_blocker_pairs(
        self,
        window: TimeWindow,
        *,
        provider_id: Optional[str] = None,
    ) -> Tuple[List[dict], int]:
        """Return observed co-occurrence counts — descriptive only."""
        pair_counts: Counter[tuple[str, str]] = Counter()
        record_total = 0
        for record in self._queries.list_calibration_records(window, provider_id=provider_id):
            record_total += 1
            classification = record.get("classification", "")
            if classification not in ("false_positive", "false_negative"):
                continue
            blocker = record.get("failure_attribution") or classification
            for gap in record.get("behavior_gaps") or []:
                cap = str(gap).split(":")[0] if ":" in str(gap) else str(gap)
                pair_counts[(cap, str(blocker))] += 1
        rows: List[dict] = []
        for (cap, blocker), count in pair_counts.most_common():
            rows.append(
                {
                    "capability_or_behavior": cap,
                    "associated_blocker": blocker,
                    "co_occurrence_count": count,
                    "interpretation": "observed correlation — not causal",
                }
            )
        return rows, record_total

    def false_positive_by_behavior(
        self,
        window: TimeWindow,
        *,
        provider_id: Optional[str] = None,
    ) -> Tuple[Counter[str], int]:
        counts: Counter[str] = Counter()
        fp_total = 0
        for record in self._queries.list_calibration_records(window, provider_id=provider_id):
            if record.get("classification") != "false_positive":
                continue
            fp_total += 1
            for gap in record.get("behavior_gaps") or []:
                counts[str(gap)] += 1
        return counts, fp_total

    def sample_size_for_pairs(self, pairs: List[dict], denominator: int) -> SampleSize:
        numerator = sum(p["co_occurrence_count"] for p in pairs)
        return SampleSize(
            numerator=numerator,
            denominator=max(denominator, numerator),
            label="co_occurrence_observations",
        )
