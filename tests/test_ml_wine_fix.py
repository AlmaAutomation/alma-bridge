from __future__ import annotations

from unittest.mock import patch

from alma_bridge.execution.wine_process import wine_rundll32_active
from alma_bridge.learning.orchestrator import (
    _AUTO_FIX_SIGNATURES,
    _maybe_apply_immediate_wine_fix,
)


def test_auto_fix_signatures_include_dotnet_and_int3():
    assert "dotnet_missing" in _AUTO_FIX_SIGNATURES
    assert "wine_int3_crash" in _AUTO_FIX_SIGNATURES


def test_immediate_wine_fix_applies_once():
    applied: set[str] = set()
    with patch("alma_bridge.learning.orchestrator.apply_ml_wine_fix") as mock_fix:
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
        mock_fix.assert_called_once()


def test_wine_rundll32_active_false_without_prefix():
    assert wine_rundll32_active("/nonexistent/prefix-xyz") is False
