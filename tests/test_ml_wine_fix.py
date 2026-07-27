from __future__ import annotations

from alma_bridge.execution.wine_process import wine_rundll32_active
from alma_bridge.learning.orchestrator import (
    _AUTO_FIX_SIGNATURES,
    _maybe_apply_immediate_wine_fix,
)


def test_auto_fix_signatures_include_dotnet_and_int3():
    assert "dotnet_missing" in _AUTO_FIX_SIGNATURES
    assert "wine_int3_crash" in _AUTO_FIX_SIGNATURES


def test_immediate_wine_fix_applies_once(monkeypatch):
    applied: set[str] = set()
    calls: list[tuple] = []

    def _record_fix(*args, **kwargs):
        calls.append((args, kwargs))
        return True

    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator.apply_ml_wine_fix",
        _record_fix,
    )
    assert _maybe_apply_immediate_wine_fix(
        "sess",
        "dotnet_missing",
        "/tmp/prefix",
        "/tmp/ascension-setup.exe",
        applied,
    )
    assert not _maybe_apply_immediate_wine_fix(
        "sess",
        "dotnet_missing",
        "/tmp/prefix",
        "/tmp/ascension-setup.exe",
        applied,
    )
    assert len(calls) == 1


def test_wine_rundll32_active_false_without_prefix():
    assert wine_rundll32_active("/nonexistent/prefix-xyz") is False
