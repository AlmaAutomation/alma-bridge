"""Aggregate statistics from compatibility evidence."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

from alma_bridge.compatibility_intelligence.apis import classify_import
from alma_bridge.compatibility_intelligence.behavior_requirements import list_behavior_profiles
from alma_bridge.compatibility_intelligence.models import (
    ImplementationStatus,
    ProvenanceEvidence,
)
from alma_bridge.compatibility_intelligence.metrics import compute_registry_metrics

from alma_bridge.research.models import SampleSize, TimeWindow
from alma_bridge.research.queries import ResearchQueries


def compute_confidence(numerator: int, denominator: int, *, min_threshold: int = 10) -> Tuple[float, List[str]]:
    factors: List[str] = []
    if denominator <= 0:
        factors.append("no_observations_in_window")
        return 0.0, factors
    ratio = min(1.0, numerator / max(min_threshold, 1))
    if numerator < min_threshold:
        factors.append(f"sample_below_threshold(n={numerator},threshold={min_threshold})")
    else:
        factors.append(f"sample_meets_threshold(n={numerator})")
    if denominator > numerator:
        factors.append(f"partial_coverage({numerator}/{denominator})")
    return round(ratio, 4), factors


class EvidenceAnalytics:
    """Deterministic aggregations over read-only evidence."""

    def __init__(self, queries: Optional[ResearchQueries] = None) -> None:
        self._queries = queries or ResearchQueries()

    def unsupported_behavior_counts(
        self,
        window: TimeWindow,
        *,
        provider_id: Optional[str] = None,
    ) -> Tuple[Counter[str], int]:
        counts: Counter[str] = Counter()
        total_profiles = 0
        for profile in list_behavior_profiles():
            if provider_id and profile.provider_id != provider_id:
                continue
            total_profiles += 1
            for behavior in profile.unsupported_behaviors:
                counts[behavior] += 1
        for record in self._queries.list_calibration_records(window, provider_id=provider_id):
            for gap in record.get("behavior_gaps") or []:
                counts[str(gap)] += 1
        for analysis in self._queries.list_analyses(window):
            for cap in analysis.required_capabilities:
                if cap.native_status == ImplementationStatus.UNSUPPORTED:
                    counts[f"capability:{cap.capability_id}"] += 1
        return counts, max(total_profiles, len(self._queries.list_analyses(window)))

    def calibration_gap_counts(
        self,
        window: TimeWindow,
        *,
        provider_id: Optional[str] = None,
    ) -> Tuple[Counter[str], int]:
        counts: Counter[str] = Counter()
        records = self._queries.list_calibration_records(window, provider_id=provider_id)
        for record in records:
            classification = record.get("classification", "")
            if classification in ("false_positive", "false_negative"):
                key = record.get("failure_attribution") or classification
                counts[str(key)] += 1
            for gap in record.get("behavior_gaps") or []:
                counts[f"behavior_gap:{gap}"] += 1
        return counts, len(records)

    def unknown_api_counts(
        self,
        window: TimeWindow,
    ) -> Tuple[Counter[str], int]:
        counts: Counter[str] = Counter()
        total_imports = 0
        provenance = ProvenanceEvidence(source="research_analytics", artifact_id="unknown_apis")
        for analysis in self._queries.list_analyses(window):
            for imp in analysis.imports:
                total_imports += 1
                result = classify_import(imp.dll, imp.name, provenance=provenance)
                if result.capability_id == "api.unknown":
                    counts[f"{imp.dll}:{imp.name}"] += 1
        return counts, total_imports

    def verification_outcomes(
        self,
        window: TimeWindow,
    ) -> Tuple[int, int, int]:
        verified = 0
        failed = 0
        total = 0
        for _bundle_id, event in self._queries.list_timeline_events(
            window, event_type="VerificationCompleted"
        ):
            total += 1
            if event.metadata.get("verified"):
                verified += 1
            else:
                failed += 1
        return verified, failed, total

    def registry_snapshot(self) -> Dict[str, float]:
        metrics = compute_registry_metrics()
        return {
            "capability_count": float(metrics.capability_count),
            "native_supported_capabilities": float(metrics.native_supported_capabilities),
            "total_registry_apis": float(metrics.total_registry_apis),
            "classified_apis": float(metrics.classified_apis),
        }

    def capability_maturity_counts(self) -> Tuple[Dict[str, int], int]:
        try:
            from alma_bridge.compatibility_intelligence.governance.repository import (
                GovernanceRepository,
            )

            version = GovernanceRepository().get_current_version()
            counts: Dict[str, int] = defaultdict(int)
            for entry in version.entries:
                counts[entry.maturity_state.value] += 1
            return dict(counts), len(version.entries)
        except Exception:
            return {}, 0

    def expansion_backlog_stats(self) -> Tuple[int, int, int]:
        plan = self._queries.get_expansion_plan()
        if plan is None:
            return 0, 0, 0
        candidates = plan.candidates
        total = len(candidates)
        return total, 0, total

    def sample_size_from_counter(
        self, counter: Counter[str], denominator: int, *, label: str = ""
    ) -> SampleSize:
        numerator = sum(counter.values())
        return SampleSize(numerator=numerator, denominator=max(denominator, numerator), label=label)
