"""Pre-execution compatibility prediction."""

from __future__ import annotations

from typing import List, Optional

from alma_bridge.compatibility_intelligence.confidence import ConfidenceScorer
from alma_bridge.compatibility_intelligence.coverage_validation import compute_coverage_validation
from alma_bridge.compatibility_intelligence.models import (
    CompatibilityPrediction,
    ConfidenceAssessment,
    CoverageReport,
    ImplementationStatus,
    PeAnalysisMetadata,
    ProvenanceEvidence,
)
from alma_bridge.compatibility_intelligence.capabilities import provider_status


PREDICTION_ENGINE_VERSION = "aci_prediction_v1"


class CompatibilityPredictor:
    """Predict provider compatibility before execution."""

    def __init__(self, scorer: Optional[ConfidenceScorer] = None) -> None:
        self._scorer = scorer or ConfidenceScorer()

    def predict(
        self,
        coverage: CoverageReport,
        metadata: PeAnalysisMetadata,
        *,
        historical_verification: bool = False,
        regression_detected: bool = False,
        provenance: ProvenanceEvidence | None = None,
        imports: list | None = None,
        classifications: list | None = None,
        required_capabilities: list | None = None,
        provider_id: str | None = None,
        fixture_name: str | None = None,
        prior_false_positive_rate: float = 0.0,
    ) -> CompatibilityPrediction:
        prov = provenance or ProvenanceEvidence(
            source="aci_prediction_engine",
            artifact_id=PREDICTION_ENGINE_VERSION,
        )

        native = coverage.providers.get("native_alma")
        wine = coverage.providers.get("wine")

        native_compatible = self._is_compatible(native)
        wine_compatible = self._is_compatible(wine)
        needs_unsupported = bool(coverage.unsupported_api_names) or (
            native is not None and native.unsupported > 0
        )

        blockers = self._collect_blockers(coverage, metadata)

        behavior_cov_pct: float | None = None
        behavior_gaps: list[str] = []
        if imports is not None and classifications is not None and required_capabilities is not None:
            selected_provider = provider_id or "native_alma"
            validation = compute_coverage_validation(
                coverage,
                required_capabilities,
                imports,
                classifications,
                metadata,
                provider_id=selected_provider,
                fixture_name=fixture_name,
            )
            behavior_cov_pct = validation.behavior_coverage_percent
            behavior_gaps = validation.behavior_gaps
            for gap in behavior_gaps:
                blockers.append(f"behavior_gap:{gap}")

        if native_compatible and (native.coverage_percent if native else 0) >= (
            wine.coverage_percent if wine else 0
        ):
            recommended = "native_alma"
            confidence = self._scorer.score(
                coverage,
                provider_id="native_alma",
                historical_verification=historical_verification,
                regression_detected=regression_detected,
                behavior_coverage_percent=behavior_cov_pct,
                behavior_gaps=behavior_gaps,
                prior_false_positive_rate=prior_false_positive_rate,
                provenance=prov,
            )
        elif wine_compatible:
            recommended = "wine"
            confidence = self._scorer.score(
                coverage,
                provider_id="wine",
                historical_verification=historical_verification,
                regression_detected=regression_detected,
                behavior_coverage_percent=behavior_cov_pct,
                behavior_gaps=behavior_gaps,
                prior_false_positive_rate=prior_false_positive_rate,
                provenance=prov,
            )
        else:
            recommended = None
            confidence = self._scorer.score(
                coverage,
                provider_id="native_alma",
                historical_verification=historical_verification,
                regression_detected=regression_detected,
                behavior_coverage_percent=behavior_cov_pct,
                behavior_gaps=behavior_gaps,
                prior_false_positive_rate=prior_false_positive_rate,
                provenance=prov,
            )

        if metadata.has_clr:
            blockers.append("dotnet.clr=detected")
            if recommended == "native_alma":
                recommended = "wine" if wine_compatible else None

        summary = self._build_summary(
            native_compatible, wine_compatible, confidence, blockers
        )

        return CompatibilityPrediction(
            native_compatible=native_compatible,
            wine_compatible=wine_compatible,
            needs_unsupported_apis=needs_unsupported,
            confidence=confidence,
            potential_blockers=sorted(set(blockers)),
            recommended_provider_id=recommended,
            evidence_summary=summary,
        )

    def _is_compatible(self, provider) -> bool:
        if provider is None:
            return False
        if provider.unsupported > 0:
            return False
        if provider.unknown > 0:
            return False
        return provider.coverage_percent >= 99.0 or (
            provider.supported + provider.partial + provider.delegated
        ) == provider.total

    def _collect_blockers(
        self,
        coverage: CoverageReport,
        metadata: PeAnalysisMetadata,
    ) -> List[str]:
        blockers: List[str] = []
        for api in coverage.unknown_api_names:
            blockers.append(f"unknown_api:{api}")
        for api in coverage.unsupported_api_names:
            blockers.append(f"unsupported_api:{api}")
        if metadata.has_tls:
            blockers.append("pe_feature:tls_callbacks")
        if metadata.delay_import_dlls:
            blockers.append("pe_feature:delay_imports")
        if metadata.subsystem.lower().find("gui") >= 0:
            status = provider_status("gui.windowing", "native_alma")
            if status == ImplementationStatus.UNSUPPORTED:
                blockers.append("subsystem:gui_requires_wine")
        return blockers

    def _build_summary(
        self,
        native_ok: bool,
        wine_ok: bool,
        confidence: ConfidenceAssessment,
        blockers: List[str],
    ) -> str:
        parts = [
            f"native={'yes' if native_ok else 'no'}",
            f"wine={'yes' if wine_ok else 'no'}",
            f"confidence={confidence.level.value}({confidence.score})",
        ]
        if blockers:
            parts.append(f"blockers={len(blockers)}")
        return "; ".join(parts)
