"""Deterministic confidence scoring — no ML."""

from __future__ import annotations

from alma_bridge.compatibility_intelligence.models import (
    ConfidenceAssessment,
    ConfidenceLevelName,
    CoverageReport,
    ImplementationStatus,
    ProvenanceEvidence,
)


CONFIDENCE_ENGINE_VERSION = "aci_confidence_deterministic_v1"


class ConfidenceScorer:
    """Evidence-based confidence from coverage, unknowns, and provider maturity."""

    WEIGHT_COVERAGE = 0.50
    WEIGHT_UNKNOWN_PENALTY = 0.20
    WEIGHT_UNSUPPORTED_PENALTY = 0.25
    WEIGHT_PROVIDER_MATURITY = 0.15
    WEIGHT_EVIDENCE_QUALITY = 0.10
    FULL_COVERAGE_BONUS = 0.29

    PROVIDER_MATURITY = {
        "native_alma": 0.7,
        "wine": 0.9,
        "proton": 0.85,
        "container": 0.6,
    }

    def score(
        self,
        coverage: CoverageReport,
        *,
        provider_id: str = "native_alma",
        historical_verification: bool = False,
        regression_detected: bool = False,
        provenance: ProvenanceEvidence | None = None,
    ) -> ConfidenceAssessment:
        prov = provenance or ProvenanceEvidence(
            source="aci_confidence_engine",
            artifact_id=CONFIDENCE_ENGINE_VERSION,
        )
        provider = coverage.providers.get(provider_id)
        factors: list[str] = []
        score = 0.0

        if provider:
            cov_frac = provider.coverage_percent / 100.0
            score += self.WEIGHT_COVERAGE * cov_frac
            factors.append(f"coverage_{provider_id}={provider.coverage_percent}%")

            if provider.coverage_percent >= 100.0 and provider.unsupported == 0 and provider.unknown == 0:
                score += self.FULL_COVERAGE_BONUS
                factors.append("full_coverage_bonus=applied")

            if provider.unknown > 0:
                penalty = min(1.0, provider.unknown / max(provider.total, 1))
                score -= self.WEIGHT_UNKNOWN_PENALTY * penalty
                factors.append(f"unknown_capabilities={provider.unknown}")

            if provider.unsupported > 0:
                penalty = min(1.0, provider.unsupported / max(provider.total, 1))
                score -= self.WEIGHT_UNSUPPORTED_PENALTY * penalty
                factors.append(f"unsupported_capabilities={provider.unsupported}")

        maturity = self.PROVIDER_MATURITY.get(provider_id, 0.5)
        score += self.WEIGHT_PROVIDER_MATURITY * maturity
        factors.append(f"provider_maturity={provider_id}:{maturity}")

        evidence_quality = 0.5
        if coverage.known_apis == coverage.total_apis and coverage.total_apis > 0:
            evidence_quality = 1.0
        elif coverage.known_apis > 0:
            evidence_quality = coverage.known_apis / coverage.total_apis
        score += self.WEIGHT_EVIDENCE_QUALITY * evidence_quality
        factors.append(f"evidence_quality={evidence_quality:.2f}")

        if historical_verification:
            score = min(1.0, score + 0.05)
            factors.append("historical_verification=boost")

        if regression_detected:
            score = max(0.0, score - 0.15)
            factors.append("regression_history=penalty")

        score = max(0.0, min(1.0, round(score, 4)))
        level = self._level_from_score(score, provider)
        factors.sort()

        return ConfidenceAssessment(
            level=level,
            score=score,
            factors=factors,
            provenance=prov,
        )

    def _level_from_score(
        self,
        score: float,
        provider: object | None,
    ) -> ConfidenceLevelName:
        if provider and getattr(provider, "unknown", 0) == getattr(provider, "total", 1):
            return ConfidenceLevelName.UNKNOWN
        if score >= 0.90:
            return ConfidenceLevelName.VERY_HIGH
        if score >= 0.75:
            return ConfidenceLevelName.HIGH
        if score >= 0.50:
            return ConfidenceLevelName.MEDIUM
        if score >= 0.25:
            return ConfidenceLevelName.LOW
        return ConfidenceLevelName.UNKNOWN
