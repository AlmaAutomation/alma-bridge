"""Regression: full-suite runs must not leak mocks or developer paths."""

from __future__ import annotations

import importlib
import inspect
import sys

import pytest

from alma_bridge.learning import orchestrator as orchestrator_module
from alma_bridge.learning.orchestrator import apply_ml_wine_fix


def test_apply_ml_wine_fix_is_real_callable_after_collection():
    """Other tests must not leave a Mock bound on orchestrator.apply_ml_wine_fix."""
    assert callable(apply_ml_wine_fix)
    assert inspect.isfunction(apply_ml_wine_fix) or inspect.isbuiltin(apply_ml_wine_fix)
    assert getattr(orchestrator_module, "apply_ml_wine_fix") is apply_ml_wine_fix


def test_orchestrator_module_survives_intelligence_import_boundary():
    """Import-boundary tests must not orphan the collected orchestrator module."""
    modules = (
        "alma_bridge.api.intelligence_routes",
        "alma_bridge.learning.orchestrator",
    )
    saved = {mod: sys.modules.get(mod) for mod in modules}
    try:
        for mod in modules:
            sys.modules.pop(mod, None)
        importlib.import_module("alma_bridge.api.intelligence_routes")
    finally:
        for mod, previous in saved.items():
            if previous is None:
                sys.modules.pop(mod, None)
            else:
                sys.modules[mod] = previous

    assert sys.modules["alma_bridge.learning.orchestrator"] is orchestrator_module


def test_monkeypatch_reaches_orchestrator_after_import_boundary(monkeypatch):
    """execute_attempt patches must bind to the same module BridgeOrchestrator uses."""
    seen: list[str] = []

    def fake_execute(**kwargs):
        seen.append("patched")
        return {
            "success": True,
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "duration_ms": 1,
            "error_signature": None,
            "likely_causes": [],
        }

    modules = (
        "alma_bridge.api.intelligence_routes",
        "alma_bridge.learning.orchestrator",
    )
    saved = {mod: sys.modules.get(mod) for mod in modules}
    try:
        for mod in modules:
            sys.modules.pop(mod, None)
        importlib.import_module("alma_bridge.api.intelligence_routes")
    finally:
        for mod, previous in saved.items():
            if previous is None:
                sys.modules.pop(mod, None)
            else:
                sys.modules[mod] = previous

    monkeypatch.setattr("alma_bridge.learning.orchestrator.execute_attempt", fake_execute)
    assert orchestrator_module.execute_attempt is fake_execute
