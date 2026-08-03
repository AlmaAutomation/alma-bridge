"""Bounded impact estimates — blocker removal language only."""

from __future__ import annotations

from alma_bridge.compatibility_intelligence.expansion.demand import DemandEvidence
from alma_bridge.compatibility_intelligence.expansion.models import (
    BoundedImpactEstimate,
    DemandCounts,
)


def compute_bounded_impact(
    demand: DemandCounts,
    evidence: DemandEvidence,
    *,
    behavior_coverage_before: float = 0.0,
    behavior_coverage_after: float = 0.0,
) -> BoundedImpactEstimate:
    """Estimate bounded impact from observed demand — not guaranteed compatibility."""
    analyses_count = len(evidence.analysis_digests)
    ineligible_count = demand.blocked_session_count + demand.false_positive_gap_count
    calibration_resolved = demand.false_positive_gap_count
    coverage_delta = max(0.0, round(behavior_coverage_after - behavior_coverage_before, 2))

    summary_parts = []
    if analyses_count > 0:
        summary_parts.append(
            f"Could remove the currently identified blocker for {analyses_count} "
            f"analysis{'ies' if analyses_count != 1 else ''}"
        )
    if ineligible_count > 0:
        summary_parts.append(
            f"estimated bounded impact: up to {ineligible_count} session(s) may move "
            f"from ineligible toward eligible (engineering candidate — not a compatibility guarantee)"
        )
    if calibration_resolved > 0:
        summary_parts.append(
            f"{calibration_resolved} calibration gap(s) potentially resolved"
        )
    if not summary_parts:
        summary_parts.append(
            "No identified blocker removal estimated from current evidence"
        )

    return BoundedImpactEstimate(
        analyses_blocker_removable=analyses_count,
        binaries_ineligible_to_eligible=ineligible_count,
        behavior_coverage_increase_percent=coverage_delta,
        calibration_gaps_potentially_resolved=calibration_resolved,
        impact_summary="; ".join(summary_parts),
    )


def normalize_impact_score(impact: BoundedImpactEstimate, *, max_reference: int = 10) -> float:
    if impact.analyses_blocker_removable <= 0:
        return 0.0
    raw = impact.analyses_blocker_removable / max_reference
    bonus = min(0.2, impact.calibration_gaps_potentially_resolved * 0.05)
    return round(min(1.0, raw + bonus), 4)
