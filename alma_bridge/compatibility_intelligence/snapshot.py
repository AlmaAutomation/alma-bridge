"""Build immutable prediction snapshots from ACI analysis results."""

from __future__ import annotations

from typing import Optional

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.compatibility_intelligence.apis import REGISTRY_VERSION
from alma_bridge.compatibility_intelligence.coverage_validation import compute_coverage_validation
from alma_bridge.compatibility_intelligence.models import (
    ACI_CALIBRATION_SCHEMA_VERSION,
    CompatibilityAnalysisResult,
    ImplementationStatus,
    PredictionSnapshot,
    StaticCoverageSnapshot,
)
from alma_bridge.compatibility_intelligence.calibration_repository import (
    CalibrationRepository,
    _utc_now_iso,
)
from alma_bridge.compatibility_intelligence.capabilities import (
    get_governance_registry_version,
    provider_status,
)


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
    fixture_name: Optional[str] = None,
) -> PredictionSnapshot:
    """Create an immutable prediction snapshot bound to exact binary and registry versions."""
    provider = analysis.coverage.providers.get(provider_id)
    symbol_cov = provider.coverage_percent if provider else 0.0

    behavior_validation = compute_coverage_validation(
        analysis.coverage,
        analysis.required_capabilities,
        analysis.imports,
        analysis.api_classifications,
        analysis.metadata,
        provider_id=provider_id,
        fixture_name=fixture_name,
    )

    static = StaticCoverageSnapshot(
        symbol_coverage_percent=symbol_cov,
        capability_coverage_percent=behavior_validation.capability_coverage_percent,
        behavior_coverage_percent=behavior_validation.behavior_coverage_percent,
        verified_scenario_coverage_percent=behavior_validation.verified_scenario_coverage_percent,
        unknown_api_count=behavior_validation.unknown_api_count,
        unresolved_dynamic_behavior_count=behavior_validation.unresolved_dynamic_behavior_count,
        behavior_gaps=behavior_validation.behavior_gaps,
        providers=dict(analysis.coverage.providers),
    )

    ts = created_at or _utc_now_iso()
    registry_version = get_governance_registry_version()
    payload = {
        "schema": ACI_CALIBRATION_SCHEMA_VERSION,
        "analysis_digest": analysis.analysis_id,
        "binary_digest": analysis.binary_digest,
        "provider_id": provider_id,
        "provider_version": PROVIDER_VERSIONS.get(provider_id, "unknown"),
        "capability_registry_version": registry_version,
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
        capability_registry_version=registry_version,
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
