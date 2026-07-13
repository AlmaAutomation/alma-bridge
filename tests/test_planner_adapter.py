"""Planner adapter tests."""

from __future__ import annotations

import pytest

from alma_bridge.session.services.planner import PlannerAdapterError, plan_from_legacy_dicts


def test_plan_from_legacy_dicts_accepts_valid_plan():
    plan = plan_from_legacy_dicts(
        "/tmp/game.exe",
        [
            {
                "strategy_id": "wine_host",
                "runtime": "wine",
                "mode": "host",
                "command": ["wine", "/tmp/game.exe"],
                "env": {},
            }
        ],
    )
    assert plan.primary is not None
    assert plan.primary.strategy_id == "wine_host"


def test_plan_from_legacy_dicts_rejects_malformed():
    with pytest.raises(PlannerAdapterError):
        plan_from_legacy_dicts("/tmp/game.exe", [{"strategy_id": "x"}])
