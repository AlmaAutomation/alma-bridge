"""Planner integration tests."""

from __future__ import annotations

from alma_bridge.compatibility_intelligence.planner_integration import (
    annotate_plans_with_capability_analysis,
    capability_requirements_from_analysis,
    select_provider_from_capabilities,
)
from alma_bridge.compatibility_intelligence.service import CompatibilityIntelligenceService
from alma_bridge.runtime.registry import build_default_registry


class TestPlannerIntegration:
    def test_annotate_plans_adds_capability_fields(self, hello64_path):
        plans = [{"strategy_id": "native_alma_console", "rank": 1}]
        enriched = annotate_plans_with_capability_analysis(
            plans, str(hello64_path)
        )
        assert len(enriched) == 1
        plan = enriched[0]
        assert "capability_analysis_id" in plan
        assert "required_capabilities" in plan
        assert "native_coverage_percent" in plan
        assert plan["native_coverage_percent"] == 100.0
        assert "aci_recommended_provider" in plan
        assert "aci_eligible_providers" in plan

    def test_select_provider_from_capabilities(self, hello64_path):
        svc = CompatibilityIntelligenceService()
        analysis = svc.analyze(str(hello64_path), persist=False)
        provider = select_provider_from_capabilities(
            analysis, registry=build_default_registry()
        )
        assert provider in {"native_alma", "wine"}

    def test_capability_requirements_console(self, hello64_path):
        svc = CompatibilityIntelligenceService()
        analysis = svc.analyze(str(hello64_path), persist=False)
        req = capability_requirements_from_analysis(analysis)
        assert "pe_console" in req.required
