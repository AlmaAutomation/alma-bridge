"""Deterministic calibration classification and failure attribution."""

from __future__ import annotations

from typing import List, Optional

from alma_bridge.compatibility_intelligence.models import (
    CalibrationClassification,
    FailureAttribution,
    OutcomeLink,
    OutcomeType,
    PredictionSnapshot,
)


AUTHORITATIVE_OUTCOMES = {
    OutcomeType.VERIFIED_SUCCESS,
    OutcomeType.VERIFIED_FAILURE,
}


def classify_calibration(
    snapshot: PredictionSnapshot,
    outcome: OutcomeLink,
) -> CalibrationClassification:
    """Classify prediction vs authoritative verification outcome."""
    if snapshot.binary_digest != outcome.binary_digest:
        return CalibrationClassification.INDETERMINATE
    if snapshot.provider_id != outcome.provider_id:
        return CalibrationClassification.INDETERMINATE
    if outcome.outcome_type not in AUTHORITATIVE_OUTCOMES:
        return CalibrationClassification.INDETERMINATE

    predicted = snapshot.predicted_eligible
    if outcome.outcome_type == OutcomeType.VERIFIED_SUCCESS:
        if predicted:
            return CalibrationClassification.TRUE_POSITIVE
        return CalibrationClassification.FALSE_NEGATIVE
    if outcome.outcome_type == OutcomeType.VERIFIED_FAILURE:
        if predicted:
            return CalibrationClassification.FALSE_POSITIVE
        return CalibrationClassification.TRUE_NEGATIVE
    return CalibrationClassification.INDETERMINATE


def attribute_failure(
    snapshot: PredictionSnapshot,
    outcome: OutcomeLink,
    *,
    classification: CalibrationClassification,
) -> Optional[FailureAttribution]:
    """Attribute false positive gaps with evidence — unknown when insufficient."""
    if classification != CalibrationClassification.FALSE_POSITIVE:
        return None

    if snapshot.static_coverage.behavior_gaps:
        return FailureAttribution.FILESYSTEM_SEMANTICS_GAP

    if snapshot.unknown_apis:
        return FailureAttribution.API_SEMANTICS_INCOMPLETE

    if snapshot.unsupported_capabilities:
        return FailureAttribution.CAPABILITY_DECLARED_TOO_BROADLY

    if outcome.failure_signature:
        sig = outcome.failure_signature.lower()
        if "loader" in sig or "pe_" in sig:
            return FailureAttribution.LOADER_GAP
        if "abi" in sig:
            return FailureAttribution.ABI_GAP
        if "verification" in sig:
            return FailureAttribution.VERIFICATION_CONTRACT_MISMATCH
        if "environment" in sig:
            return FailureAttribution.PROCESS_ENVIRONMENT_GAP

    if snapshot.blockers:
        for blocker in snapshot.blockers:
            if blocker.startswith("behavior_gap:"):
                return FailureAttribution.FILESYSTEM_SEMANTICS_GAP
            if "delay_import" in blocker:
                return FailureAttribution.UNSUPPORTED_DYNAMIC_IMPORT
            if "tls" in blocker:
                return FailureAttribution.SYNCHRONIZATION_GAP

    return FailureAttribution.UNKNOWN
