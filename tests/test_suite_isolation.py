"""Regression: full-suite runs must not leak mocks or developer paths."""

from __future__ import annotations

import inspect

from alma_bridge.learning import orchestrator as orchestrator_module
from alma_bridge.learning.orchestrator import apply_ml_wine_fix


def test_apply_ml_wine_fix_is_real_callable_after_collection():
    """Other tests must not leave a Mock bound on orchestrator.apply_ml_wine_fix."""
    assert callable(apply_ml_wine_fix)
    assert inspect.isfunction(apply_ml_wine_fix) or inspect.isbuiltin(apply_ml_wine_fix)
    assert getattr(orchestrator_module, "apply_ml_wine_fix") is apply_ml_wine_fix
