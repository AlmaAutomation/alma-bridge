"""Planner runtime capability selection tests."""

from __future__ import annotations

from alma_bridge.runtime.planner_bridge import (
    annotate_plan_with_runtime_providers,
    build_execution_plan_with_runtime,
)
from alma_bridge.runtime.registry import build_default_registry
from alma_bridge.runtime.selection import (
    provider_id_for_strategy,
    select_provider_for_strategy,
)


class TestPlannerRuntimeSelection:
    def test_strategy_to_provider_mapping(self):
        assert provider_id_for_strategy("wine_host") == "wine"
        assert provider_id_for_strategy("proton_host") == "proton"
        assert provider_id_for_strategy("container_compat") == "container"
        assert provider_id_for_strategy("native_host") is None

    def test_select_provider_for_wine_strategy(self):
        reg = build_default_registry()
        provider = select_provider_for_strategy("wine_host", reg)
        if provider:
            assert provider.provider_id == "wine"

    def test_annotate_plan_preserves_strategy_ids(self):
        plans = [
            {
                "strategy_id": "wine_host",
                "runtime": "wine",
                "mode": "host",
                "command": ["wine", "/tmp/game.exe"],
                "env": {},
            }
        ]
        annotated = annotate_plan_with_runtime_providers(plans)
        assert annotated[0]["strategy_id"] == "wine_host"
        assert annotated[0]["runtime_provider_id"] == "wine"

    def test_build_execution_plan_with_runtime_additive(self):
        plans = build_execution_plan_with_runtime(
            "/home/joshua/Documents/WoW.exe",
        )
        assert plans
        assert "strategy_id" in plans[0]
        assert "runtime_provider_id" in plans[0]
