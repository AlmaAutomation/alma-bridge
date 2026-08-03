"""Conformance baseline comparison engine."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from alma_bridge.runtime.conformance.models import ConformanceClassification


def classify_baseline_comparison(
    *,
    baseline: Dict[str, Any],
    candidate: Dict[str, Any],
    required_signals: Optional[List[str]] = None,
) -> ConformanceClassification:
    """Classify candidate behavior relative to a baseline run."""
    signals = required_signals or []
    if not baseline and not candidate:
        return ConformanceClassification.INSUFFICIENT_EVIDENCE

    if candidate.get("error") or candidate.get("failed"):
        return ConformanceClassification.CANDIDATE_FAILED

    missing = [signal for signal in signals if signal not in baseline and signal not in candidate]
    if missing and not baseline:
        return ConformanceClassification.INSUFFICIENT_EVIDENCE

    baseline_exit = baseline.get("exit_code")
    candidate_exit = candidate.get("exit_code")
    if baseline_exit is not None and candidate_exit is not None:
        if baseline_exit == candidate_exit:
            baseline_out = str(baseline.get("stdout") or "")
            candidate_out = str(candidate.get("stdout") or "")
            if baseline_out == candidate_out:
                return ConformanceClassification.EQUIVALENT
            return ConformanceClassification.FUNCTIONALLY_EQUIVALENT
        return ConformanceClassification.BEHAVIOR_CHANGED

    if baseline and candidate:
        overlap = set(baseline.keys()) & set(candidate.keys())
        if overlap:
            return ConformanceClassification.PARTIALLY_EQUIVALENT

    return ConformanceClassification.INSUFFICIENT_EVIDENCE
