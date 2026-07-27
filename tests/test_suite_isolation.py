"""Regression: full-suite runs must not leak mocks or developer paths.

These tests guard against order-dependent failures that pass in isolation but
fail under ``pytest -q``. See ``docs/reviews/full-suite-test-isolation-triage.md``
(2026-07-27): nine orchestration and verification tests failed together because
``test_import_intelligence_routes_does_not_load_orchestrator`` popped
``alma_bridge.learning.orchestrator`` from ``sys.modules`` without restoring it.

That left collection-time ``BridgeOrchestrator`` instances (and
``api.routes.orchestrator``) bound to a stale module object while later
``monkeypatch.setattr("alma_bridge.learning.orchestrator.*", ...)`` calls patched
a freshly re-imported module in ``sys.modules``. The tests below look redundant
when run alone; they exist so that regression is caught before the next import-
boundary experiment silently orphans shared modules again.
"""

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
    """sys.modules pops must restore the orchestrator module pytest collected.

    Without this, import-boundary tests can leave ``sys.modules`` pointing at a
    different ``orchestrator`` object than ``BridgeOrchestrator`` and test
    imports hold. Full-suite monkeypatches then miss live orchestration paths.
    """
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
    """monkeypatch must hit the same module object orchestration code executes.

    Replays the intelligence import-boundary pattern and asserts
    ``monkeypatch.setattr("alma_bridge.learning.orchestrator.execute_attempt", ...)``
    replaces the callable on the canonical module — not an orphaned re-import.
    """
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
