"""Terminal shadow observation boundary tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from alma_bridge.learning.orchestrator import BridgeOrchestrator
from alma_bridge.schemas.models import BridgeRequest
from alma_bridge.session.auto_compat_budget import AutoCompatibilityBudget
from alma_bridge.storage import outcomes


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    outcomes.init_outcome_store()
    yield


def _actual_count(session_id: str) -> int:
    import sqlite3
    from alma_bridge.config import settings

    conn = sqlite3.connect(settings.db_path)
    return conn.execute(
        "SELECT COUNT(*) FROM compatibility_profile_shadow_actual_outcomes WHERE session_id = ?",
        (session_id,),
    ).fetchone()[0]


@pytest.mark.parametrize("shadow_enabled", [False, True])
def test_failure_records_single_shadow_actual(monkeypatch, tmp_path, shadow_enabled):
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profiles_enabled", shadow_enabled)
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profile_shadow_mode", shadow_enabled)
    script = tmp_path / "fail.sh"
    script.write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")
    script.chmod(0o755)
    result = BridgeOrchestrator().run(
        BridgeRequest(file_path=str(script), max_attempts=1, auto_remediate=False)
    )
    assert result.success is False
    if shadow_enabled:
        assert _actual_count(result.session_id) == 1
        assert _actual_count(result.session_id) == 1
    else:
        assert _actual_count(result.session_id) == 0


def test_budget_exhaustion_records_shadow_actual(monkeypatch, tmp_path):
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profiles_enabled", True)
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profile_shadow_mode", True)
    monkeypatch.setattr("alma_bridge.config.settings.auto_compat_max_execution_attempts", 1)
    script = tmp_path / "loop.sh"
    script.write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")
    script.chmod(0o755)
    result = BridgeOrchestrator().run(
        BridgeRequest(file_path=str(script), max_attempts=5, auto_remediate=False)
    )
    assert result.success is False
    assert "AUTO_COMPATIBILITY_BUDGET_EXHAUSTED" in result.summary
    assert _actual_count(result.session_id) == 1


def test_internal_exception_records_shadow_actual(monkeypatch, tmp_path):
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profiles_enabled", True)
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profile_shadow_mode", True)
    script = tmp_path / "boom.sh"
    script.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    script.chmod(0o755)
    orchestrator = BridgeOrchestrator()
    with patch.object(orchestrator._planner, "plan", side_effect=RuntimeError("boom")):
        result = orchestrator.run(
            BridgeRequest(file_path=str(script), max_attempts=1, auto_remediate=False)
        )
    assert "internal error" in result.summary.lower()
    assert _actual_count(result.session_id) == 1
