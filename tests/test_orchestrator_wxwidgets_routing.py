"""Orchestrator routing tests for framework-aware launcher handoff."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from alma_bridge.compatibility.program_kind import IMAGE_SUBSYSTEM_WINDOWS_GUI
from alma_bridge.learning.orchestrator import BridgeOrchestrator
from alma_bridge.schemas.models import BridgeRequest, ExecutionMode
from alma_bridge.session.lifecycle import SessionLifecycleManager
from alma_bridge.session.state import SessionState
from alma_bridge.storage import outcomes
from tests.pe_test_helpers import write_minimal_pe

FIXTURE_STDERR = (
    Path(__file__).parent / "fixtures" / "codeblocks_startup_stderr.txt"
).read_text(encoding="utf-8")


def _wxwidgets_app_dir(tmp_path: Path) -> Path:
    app_dir = tmp_path / "CodeBlocks"
    app_dir.mkdir()
    exe = app_dir / "codeblocks.exe"
    write_minimal_pe(exe, subsystem=IMAGE_SUBSYSTEM_WINDOWS_GUI, pe32plus=False)
    (app_dir / "wxmsw32u_gcc_custom.dll").write_bytes(b"MZ")
    return exe


def _patch_handoff_prereqs(monkeypatch, orchestrator: BridgeOrchestrator, tmp_path):
    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator.require_wine_windows_version",
        lambda _prefix: (True, "win10"),
    )
    monkeypatch.setattr("alma_bridge.learning.orchestrator._ensure_prefix_runtimes", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator, "_create_shadow_prediction_before_plan", lambda *a, **k: None)
    monkeypatch.setattr("alma_bridge.learning.orchestrator._persist_prefix_profile", lambda *a, **k: None)


def test_wxwidgets_handoff_excludes_electron_env(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.bridge_auto_remediate", False)
    monkeypatch.setattr("alma_bridge.config.settings.wine_gui_startup_timeout_sec", 0.01)
    monkeypatch.setattr("alma_bridge.config.settings.wine_gui_survival_sec", 0.01)

    launcher = _wxwidgets_app_dir(tmp_path)
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    orchestrator = BridgeOrchestrator()
    captured: dict[str, object] = {}

    def fake_execute(**kwargs):
        captured["env"] = dict(kwargs.get("env") or {})
        captured["extra_args"] = list(kwargs.get("extra_args") or [])
        return {
            "success": True,
            "exit_code": 0,
            "stdout": "",
            "stderr": FIXTURE_STDERR,
            "duration_ms": 3,
        }

    monkeypatch.setattr("alma_bridge.learning.orchestrator.execute_attempt", fake_execute)
    _patch_handoff_prereqs(monkeypatch, orchestrator, tmp_path)
    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator.build_execution_plan",
        lambda *args, **kwargs: [
            {
                "strategy_id": "wine_host",
                "runtime": "wine",
                "mode": "host",
                "command": ["wine", str(launcher)],
                "env": {},
            }
        ],
    )
    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator.prepare_electron_wine",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("prepare_electron_wine must not run for wxWidgets handoff")
        ),
    )
    monkeypatch.setattr(
        "alma_bridge.execution.wine_gui_handoff.observe_target_gui_process",
        lambda *args, **kwargs: SimpleNamespace(
            appeared=True,
            survived=True,
            to_evidence_lines=lambda: ["target_process=codeblocks.exe"],
            to_dict=lambda: {"pid": 4242},
        ),
    )

    session_id = outcomes.new_session(str(launcher), "hash", {})
    lifecycle = SessionLifecycleManager(session_id)
    lifecycle.transition(SessionState.CREATED, reason="t", expected_from=SessionState.CREATED)
    lifecycle.transition(SessionState.INSPECTING, reason="t", expected_from=SessionState.CREATED)
    lifecycle.transition(SessionState.PLANNING, reason="t", expected_from=SessionState.INSPECTING)
    lifecycle.transition(SessionState.POLICY_CHECK, reason="t", expected_from=SessionState.PLANNING)

    with patch.object(orchestrator, "_persist_profile_candidate_before_success", return_value=None):
        with patch.object(orchestrator, "_promote_profile_candidate_after_success"):
            result = orchestrator._run_launcher_handoff(
                request=BridgeRequest(file_path="/tmp/setup.exe", max_attempts=3),
                session_id=session_id,
                lifecycle=lifecycle,
                launcher_path=str(launcher),
                wine_prefix=str(prefix),
                hardware={"architecture": "x86_64"},
                started_at=datetime.now(timezone.utc),
                digest="hash",
                prior_attempts=[],
                skipped_installer=True,
            )

    env = captured.get("env", {})
    assert "ELECTRON_DISABLE_CRASH_REPORTER" not in env
    assert "ALMA_INSTALL_CS_GUARD_WORKAROUND" not in env
    assert "ALMA_INSTALL_ELEVATE_PASSTHROUGH" not in env
    assert "--disable-gpu" not in captured.get("extra_args", [])
    assert result.success is True
    assert result.attempts[0].phase == "wine_gui"
    assert result.attempts[0].mode == ExecutionMode.HOST


def test_wxwidgets_plan_does_not_require_orchestrator_app_branch(tmp_path):
    launcher = _wxwidgets_app_dir(tmp_path)
    from alma_bridge.compatibility.program_kind import classify_program_kind

    kind = classify_program_kind(str(launcher))
    assert kind["framework"] == "wxwidgets"
    assert kind["is_electron"] is False
