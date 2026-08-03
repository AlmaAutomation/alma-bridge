"""Build immutable prediction snapshots from ACI analysis results."""

from __future__ import annotations

from typing import Optional

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.compatibility_intelligence.apis import REGISTRY_VERSION
from alma_bridge.compatibility_intelligence.models import (
    ACI_CALIBRATION_SCHEMA_VERSION,
    CAPABILITY_REGISTRY_VERSION,
    CompatibilityAnalysisResult,
    ImplementationStatus,
    PredictionSnapshot,
    StaticCoverageSnapshot,
)
from alma_bridge.compatibility_intelligence.calibration_repository import (
    CalibrationRepository,
    _utc_now_iso,
)
from alma_bridge.compatibility_intelligence.capabilities import provider_status


SNAPSHOT_ENGINE_VERSION = "aci_snapshot_v1"

PROVIDER_VERSIONS = {
    "native_alma": "0.2.0-m2",
    "wine": "stable",
    "proton": "experimental",
    "container": "delegated",
}


def _delegated_capabilities(analysis: CompatibilityAnalysisResult, provider_id: str) -> list[str]:
    delegated: list[str] = []
    for req in analysis.required_capabilities:
        status = provider_status(req.capability_id, provider_id)
        if status == ImplementationStatus.DELEGATED:
            delegated.append(req.capability_id)
    return sorted(delegated)


def _unsupported_capabilities(analysis: CompatibilityAnalysisResult, provider_id: str) -> list[str]:
    unsupported: list[str] = []
    for req in analysis.required_capabilities:
        status = provider_status(req.capability_id, provider_id)
        if status == ImplementationStatus.UNSUPPORTED:
            unsupported.append(req.capability_id)
    return sorted(unsupported)


def _predicted_eligible(
    analysis: CompatibilityAnalysisResult,
    provider_id: str,
) -> bool:
    pred = analysis.prediction
    if provider_id == "native_alma":
        return pred.native_compatible
    if provider_id == "wine":
        return pred.wine_compatible
    provider = analysis.coverage.providers.get(provider_id)
    if provider is None:
        return False
    return provider.unsupported == 0 and provider.unknown == 0


def build_prediction_snapshot(
    analysis: CompatibilityAnalysisResult,
    *,
    provider_id: str,
    session_id: str = "",
    created_at: Optional[str] = None,
) -> PredictionSnapshot:
    """Create an immutable prediction snapshot bound to exact binary and registry versions."""
    provider = analysis.coverage.providers.get(provider_id)
    symbol_cov = provider.coverage_percent if provider else 0.0
    cap_cov = symbol_cov  # refined by behavior coverage in Phase 2 commit 4

    static = StaticCoverageSnapshot(
        symbol_coverage_percent=symbol_cov,
        capability_coverage_percent=cap_cov,
        providers=dict(analysis.coverage.providers),
    )

    ts = created_at or _utc_now_iso()
    payload = {
        "schema": ACI_CALIBRATION_SCHEMA_VERSION,
        "analysis_digest": analysis.analysis_id,
        "binary_digest": analysis.binary_digest,
        "provider_id": provider_id,
        "provider_version": PROVIDER_VERSIONS.get(provider_id, "unknown"),
        "capability_registry_version": CAPABILITY_REGISTRY_VERSION,
        "api_registry_version": REGISTRY_VERSION,
        "created_at": ts,
        "engine": SNAPSHOT_ENGINE_VERSION,
    }
    snapshot_id = CalibrationRepository.build_snapshot_id(payload)

    return PredictionSnapshot(
        snapshot_id=snapshot_id,
        session_id=session_id,
        analysis_digest=analysis.analysis_id,
        binary_digest=analysis.binary_digest,
        provider_id=provider_id,
        provider_version=PROVIDER_VERSIONS.get(provider_id, "unknown"),
        capability_registry_version=CAPABILITY_REGISTRY_VERSION,
        api_registry_version=REGISTRY_VERSION,
        required_capabilities=sorted(r.capability_id for r in analysis.required_capabilities),
        unsupported_capabilities=_unsupported_capabilities(analysis, provider_id),
        unknown_apis=list(analysis.coverage.unknown_api_names),
        delegated_capabilities=_delegated_capabilities(analysis, provider_id),
        static_coverage=static,
        confidence_level=analysis.prediction.confidence.level,
        confidence_score=analysis.prediction.confidence.score,
        blockers=list(analysis.prediction.potential_blockers),
        prediction=analysis.prediction,
        predicted_eligible=_predicted_eligible(analysis, provider_id),
        created_at=ts,
        engine_version=SNAPSHOT_ENGINE_VERSION,
    )
