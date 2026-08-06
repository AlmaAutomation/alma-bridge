"""Shared CLI provider decision — coverage vs eligibility vs recommendation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from alma_bridge.compatibility_intelligence.models import CompatibilityAnalysisResult
from alma_bridge.compatibility_intelligence.planner_integration import (
    capability_requirements_from_analysis,
)
from alma_bridge.runtime.registry import RuntimeRegistry, build_default_registry
from alma_bridge.runtime.selection import select_providers


_PROVIDER_PREFERENCE = ("native_alma", "wine", "proton", "container")


def is_provider_compatible(analysis: CompatibilityAnalysisResult, provider_id: str) -> bool:
    """Return True when ACI predicts the provider can run this binary."""
    pred = analysis.prediction
    if provider_id == "native_alma":
        return pred.native_compatible
    if provider_id == "wine":
        return pred.wine_compatible
    provider = analysis.coverage.providers.get(provider_id)
    if provider is None:
        return False
    if provider.unsupported > 0 or provider.unknown > 0:
        return False
    return provider.coverage_percent >= 99.0 or (
        provider.supported + provider.partial + provider.delegated
    ) == provider.total


def _highest_coverage_provider(analysis: CompatibilityAnalysisResult) -> tuple[Optional[str], float]:
    best_id: Optional[str] = None
    best_pct = -1.0
    for pid, breakdown in analysis.coverage.providers.items():
        if breakdown.coverage_percent > best_pct:
            best_pct = breakdown.coverage_percent
            best_id = pid
    if best_id is None:
        return None, 0.0
    return best_id, best_pct


def _registry_eligible_ids(
    analysis: CompatibilityAnalysisResult,
    registry: RuntimeRegistry,
) -> List[str]:
    req = capability_requirements_from_analysis(analysis)
    return [p.provider_id for p in select_providers(req, registry)]


def _pick_preferred(provider_ids: List[str]) -> Optional[str]:
    for preferred in _PROVIDER_PREFERENCE:
        if preferred in provider_ids:
            return preferred
    return provider_ids[0] if provider_ids else None


@dataclass(frozen=True)
class ProviderDecision:
    highest_coverage_provider: Optional[str]
    highest_coverage_percent: float
    highest_coverage_eligible: bool
    eligible_provider: Optional[str]
    eligible_provider_ids: List[str]
    recommended_provider: Optional[str]
    selected_execution_provider: Optional[str]
    prediction_status: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "highest_coverage_provider": self.highest_coverage_provider,
            "highest_coverage_percent": self.highest_coverage_percent,
            "highest_coverage_eligible": self.highest_coverage_eligible,
            "eligible_provider": self.eligible_provider,
            "eligible_provider_ids": list(self.eligible_provider_ids),
            "recommended_provider": self.recommended_provider,
            "selected_execution_provider": self.selected_execution_provider,
            "prediction_status": self.prediction_status,
        }


def resolve_provider_decision(
    analysis: CompatibilityAnalysisResult,
    *,
    registry: Optional[RuntimeRegistry] = None,
    explicit_provider_id: Optional[str] = None,
) -> ProviderDecision:
    """Derive consistent provider fields for analyze, inspect, and predict."""
    reg = registry or build_default_registry()
    highest_id, highest_pct = _highest_coverage_provider(analysis)

    registry_eligible = _registry_eligible_ids(analysis, reg)
    compatible_eligible = [
        pid for pid in registry_eligible if is_provider_compatible(analysis, pid)
    ]
    eligible_provider = _pick_preferred(compatible_eligible)

    predicted = analysis.prediction.recommended_provider_id
    recommended = predicted if predicted and predicted in compatible_eligible else None

    selected: Optional[str] = None
    if explicit_provider_id:
        if explicit_provider_id in compatible_eligible:
            selected = explicit_provider_id
    elif recommended:
        selected = recommended
    elif eligible_provider:
        selected = eligible_provider

    highest_eligible = bool(highest_id and highest_id in compatible_eligible)
    status = "ok" if compatible_eligible else "no_eligible_provider"

    return ProviderDecision(
        highest_coverage_provider=highest_id,
        highest_coverage_percent=highest_pct,
        highest_coverage_eligible=highest_eligible,
        eligible_provider=eligible_provider,
        eligible_provider_ids=compatible_eligible,
        recommended_provider=recommended,
        selected_execution_provider=selected,
        prediction_status=status,
    )
