"""Capability-aware planner integration."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from alma_bridge.compatibility_intelligence.models import CompatibilityAnalysisResult
from alma_bridge.compatibility_intelligence.prediction import CompatibilityPredictor
from alma_bridge.compatibility_intelligence.service import CompatibilityIntelligenceService
from alma_bridge.runtime.registry import RuntimeRegistry, build_default_registry
from alma_bridge.runtime.selection import select_providers
from alma_bridge.runtime.models import RuntimeRequirements


def capability_requirements_from_analysis(
    analysis: CompatibilityAnalysisResult,
) -> RuntimeRequirements:
    """Map ACI capability analysis to runtime provider requirements."""
    required: List[str] = []
    metadata = analysis.metadata
    if metadata.subsystem.lower().find("gui") >= 0:
        required.append("pe_gui")
    else:
        required.append("pe_console")
    if metadata.has_clr:
        required.append("pe_electron")
    return RuntimeRequirements(required=sorted(set(required)), strategy_id=None)


def annotate_plans_with_capability_analysis(
    plans: List[Dict[str, Any]],
    file_path: str,
    *,
    service: Optional[CompatibilityIntelligenceService] = None,
    registry: Optional[RuntimeRegistry] = None,
) -> List[Dict[str, Any]]:
    """Enrich execution plans with capability analysis (additive, no bypass)."""
    svc = service or CompatibilityIntelligenceService()
    reg = registry or build_default_registry()
    try:
        analysis = svc.analyze(file_path)
    except Exception:
        return plans

    cap_req = capability_requirements_from_analysis(analysis)
    eligible_providers = select_providers(cap_req, reg)
    eligible_ids = [p.provider_id for p in eligible_providers]

    enriched: List[Dict[str, Any]] = []
    for plan in plans:
        item = dict(plan)
        item["capability_analysis_id"] = analysis.analysis_id
        item["required_capabilities"] = [r.capability_id for r in analysis.required_capabilities]
        item["native_coverage_percent"] = (
            analysis.coverage.providers.get("native_alma").coverage_percent
            if analysis.coverage.providers.get("native_alma")
            else 0.0
        )
        item["wine_coverage_percent"] = (
            analysis.coverage.providers.get("wine").coverage_percent
            if analysis.coverage.providers.get("wine")
            else 0.0
        )
        item["prediction_confidence"] = analysis.prediction.confidence.level.value
        item["aci_recommended_provider"] = analysis.prediction.recommended_provider_id
        item["aci_eligible_providers"] = eligible_ids
        item["aci_blockers"] = analysis.prediction.potential_blockers
        enriched.append(item)
    return enriched


def select_provider_from_capabilities(
    analysis: CompatibilityAnalysisResult,
    registry: Optional[RuntimeRegistry] = None,
) -> Optional[str]:
    """Select best provider from capability analysis without bypassing registry."""
    reg = registry or build_default_registry()
    req = capability_requirements_from_analysis(analysis)
    providers = select_providers(req, reg)
    if not providers:
        return None
    provider_ids = [p.provider_id for p in providers]
    predicted = analysis.prediction.recommended_provider_id
    if predicted and predicted in provider_ids:
        return predicted
    # Prefer native_alma or wine for PE console when both are eligible.
    for preferred in ("native_alma", "wine", "proton", "container"):
        if preferred in provider_ids:
            return preferred
    return providers[0].provider_id
