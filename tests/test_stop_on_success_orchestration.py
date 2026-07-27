"""Regression tests for stop-on-success orchestration invariants."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from alma_bridge.compatibility.program_kind import IMAGE_SUBSYSTEM_WINDOWS_GUI
from alma_bridge.learning.orchestrator import BridgeOrchestrator, _persist_attempt
from alma_bridge.schemas.models import (
    AttemptRecord,
    BridgeRequest,
    BridgeSessionResult,
    ExecutionMode,
)
from alma_bridge.session.lifecycle import SessionLifecycleManager
from alma_bridge.session.services.planner import ExecutionPlan, ExecutionPlanStep
from alma_bridge.session.services.routes import RouteExecutionResult
from alma_bridge.session.state import SessionState
from alma_bridge.session.verification_gateway import declare_verified_session_success
from alma_bridge.storage import outcomes
from tests.pe_test_helpers import write_minimal_pe


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    outcomes.init_outcome_store()
    yield


def _mock_plan(*, strategies: list[str]) -> ExecutionPlan:
    return ExecutionPlan(
        file_path="app.exe",
        steps=[
            ExecutionPlanStep(
                strategy_id=strategy_id,
                runtime="wine",
                mode="host" if strategy_id == "wine_host" else "container",
                description=strategy_id,
                command=["wine", "app.exe"],
                env={},
            )
            for strategy_id in strategies
        ],
    )


def _wine_gui_exe(tmp_path) -> str:
    exe = tmp_path / "codeblocks.exe"
    write_minimal_pe(exe, subsystem=IMAGE_SUBSYSTEM_WINDOWS_GUI)
    return str(exe)


def _setup_succeeded_session(
    session_id: str,
    *,
    winning: AttemptRecord,
) -> SessionLifecycleManager:
    lifecycle = SessionLifecycleManager(session_id)
    for state, prev in [
        (SessionState.CREATED, SessionState.CREATED),
        (SessionState.INSPECTING, SessionState.CREATED),
        (SessionState.PLANNING, SessionState.INSPECTING),
        (SessionState.POLICY_CHECK, SessionState.PLANNING),
        (SessionState.EXECUTING, SessionState.POLICY_CHECK),
        (SessionState.OBSERVING, SessionState.EXECUTING),
        (SessionState.VERIFYING, SessionState.OBSERVING),
    ]:
        lifecycle.transition(state, reason="test", expected_from=prev)
    declare_verified_session_success(
        lifecycle=lifecycle,
        session_id=session_id,
        transition=lambda lc, st, **kw: lc.transition(
            st, reason=kw.get("reason", "test"), expected_from=lc.state
        ),
        summary="verified ok",
    )
    _persist_attempt(
        session_id,
        winning,
        verification={"passed": True, "confidence": 0.95, "checks": [], "evidence": ["ok"]},
    )
    return lifecycle


def _failed_attempt(n: int, *, phase: str = "wine_gui", signature: str = "gui_process_not_found") -> AttemptRecord:
    return AttemptRecord(
        attempt_number=n,
        strategy_id="wine_host",
        runtime="wine",
        command=["wine", "app.exe"],
        mode=ExecutionMode.HOST,
        success=False,
        stderr=signature,
        error_signature=signature,
        phase=phase,
    )


def _successful_attempt(n: int, *, phase: str = "wine_gui") -> AttemptRecord:
    return AttemptRecord(
        attempt_number=n,
        strategy_id="wine_host",
        runtime="wine",
        command=["wine", "app.exe"],
        mode=ExecutionMode.HOST,
        success=True,
        phase=phase,
    )


def _patch_gui_timeouts(monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.wine_gui_startup_timeout_sec", 0.01)
    monkeypatch.setattr("alma_bridge.config.settings.wine_gui_survival_sec", 0.01)


def _patch_handoff_prereqs(monkeypatch, orchestrator: BridgeOrchestrator, tmp_path):
    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator.require_wine_windows_version",
        lambda _prefix: (True, "win10"),
    )
    monkeypatch.setattr("alma_bridge.learning.orchestrator._ensure_prefix_runtimes", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator, "_create_shadow_prediction_before_plan", lambda *a, **k: None)
    monkeypatch.setattr("alma_bridge.learning.orchestrator._persist_prefix_profile", lambda *a, **k: None)


def _patch_run_session_prereqs(monkeypatch, orchestrator: BridgeOrchestrator, tmp_path):
    monkeypatch.setattr("alma_bridge.learning.orchestrator.fresh_prefix_path", lambda _sid: str(tmp_path / "prefix"))
    monkeypatch.setattr("alma_bridge.hardware.prefixes.find_best_prefix", lambda _path: str(tmp_path / "prefix"))
    _patch_handoff_prereqs(monkeypatch, orchestrator, tmp_path)


def test_succeeded_session_cannot_create_another_attempt():
    session_id = outcomes.new_session("/tmp/app.exe", "hash", {})
    winning = _successful_attempt(1)
    lifecycle = _setup_succeeded_session(session_id, winning=winning)

    orchestrator = BridgeOrchestrator()
    result = orchestrator._return_if_session_succeeded(
        lifecycle=lifecycle,
        session_id=session_id,
        request=BridgeRequest(file_path="/tmp/app.exe"),
        started_at=datetime.now(timezone.utc),
        digest="hash",
        hardware={},
    )

    assert result is not None
    assert result.success is True
    assert result.winning_attempt is not None
    assert result.winning_attempt.attempt_number == 1


def test_successful_first_gui_attempt_stops_remaining_strategy_iteration(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.bridge_auto_remediate", False)
    exe = _wine_gui_exe(tmp_path)
    orchestrator = BridgeOrchestrator()
    execute_calls = {"n": 0}

    def fake_execute(**kwargs):
        execute_calls["n"] += 1
        return {
            "success": True,
            "exit_code": 0,
            "stdout": "",
            "stderr": "[alma] gui detached",
            "duration_ms": 5,
        }

    _patch_run_session_prereqs(monkeypatch, orchestrator, tmp_path)
    monkeypatch.setattr("alma_bridge.learning.orchestrator.execute_attempt", fake_execute)
    monkeypatch.setattr(
        orchestrator._planner,
        "plan",
        lambda *args, **kwargs: _mock_plan(strategies=["wine_host", "container_compat"]),
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

    session_id = outcomes.new_session(exe, "hash", {})
    lifecycle = SessionLifecycleManager(session_id)
    lifecycle.transition(SessionState.CREATED, reason="t", expected_from=SessionState.CREATED)
    lifecycle.transition(SessionState.INSPECTING, reason="t", expected_from=SessionState.CREATED)
    lifecycle.transition(SessionState.PLANNING, reason="t", expected_from=SessionState.INSPECTING)

    with patch.object(orchestrator, "_persist_profile_candidate_before_success", return_value=None):
        with patch.object(orchestrator, "_promote_profile_candidate_after_success"):
            result = orchestrator._run_session(
                request=BridgeRequest(file_path=exe, max_attempts=4),
                session_id=session_id,
                lifecycle=lifecycle,
                retry_guard=MagicMock(max_attempts=4, session_timed_out=lambda: False, escalation_allowed=lambda _sig: True),
                hardware={"architecture": "x86_64"},
                started_at=datetime.now(timezone.utc),
                digest="hash",
                inspection=SimpleNamespace(recommended_strategy_id="wine_host"),
                cancel_check=None,
            )

    assert result.success is True
    assert execute_calls["n"] == 1


def test_successful_second_attempt_stops_third_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.bridge_auto_remediate", False)
    exe = _wine_gui_exe(tmp_path)
    orchestrator = BridgeOrchestrator()
    execute_calls = {"n": 0}

    def fake_execute(**kwargs):
        execute_calls["n"] += 1
        if execute_calls["n"] < 2:
            return {
                "success": False,
                "exit_code": 1,
                "stdout": "",
                "stderr": "gui_process_not_found",
                "error_signature": "gui_process_not_found",
                "duration_ms": 5,
            }
        return {
            "success": True,
            "exit_code": 0,
            "stdout": "",
            "stderr": "[alma] gui detached",
            "duration_ms": 5,
        }

    observe_calls = {"n": 0}

    def observe(*args, **kwargs):
        observe_calls["n"] += 1
        if observe_calls["n"] < 2:
            return SimpleNamespace(
                appeared=False,
                survived=False,
                to_evidence_lines=lambda: [],
                to_dict=lambda: {},
            )
        return SimpleNamespace(
            appeared=True,
            survived=True,
            to_evidence_lines=lambda: ["target_process=codeblocks.exe"],
            to_dict=lambda: {"pid": 4242},
        )

    _patch_run_session_prereqs(monkeypatch, orchestrator, tmp_path)
    monkeypatch.setattr("alma_bridge.learning.orchestrator.execute_attempt", fake_execute)
    monkeypatch.setattr(
        orchestrator._planner,
        "plan",
        lambda *args, **kwargs: _mock_plan(strategies=["wine_host"]),
    )
    monkeypatch.setattr("alma_bridge.execution.wine_gui_handoff.observe_target_gui_process", observe)

    session_id = outcomes.new_session(exe, "hash", {})
    lifecycle = SessionLifecycleManager(session_id)
    lifecycle.transition(SessionState.CREATED, reason="t", expected_from=SessionState.CREATED)
    lifecycle.transition(SessionState.INSPECTING, reason="t", expected_from=SessionState.CREATED)
    lifecycle.transition(SessionState.PLANNING, reason="t", expected_from=SessionState.INSPECTING)

    with patch.object(orchestrator, "_persist_profile_candidate_before_success", return_value=None):
        with patch.object(orchestrator, "_promote_profile_candidate_after_success"):
            result = orchestrator._run_session(
                request=BridgeRequest(file_path=exe, max_attempts=5),
                session_id=session_id,
                lifecycle=lifecycle,
                retry_guard=MagicMock(max_attempts=5, session_timed_out=lambda: False, escalation_allowed=lambda _sig: True),
                hardware={"architecture": "x86_64"},
                started_at=datetime.now(timezone.utc),
                digest="hash",
                inspection=SimpleNamespace(recommended_strategy_id="wine_host"),
                cancel_check=None,
            )

    assert result.success is True
    assert execute_calls["n"] == 2


def test_successful_nested_bridge_retry_propagates_to_parent_loop(monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.bridge_auto_remediate", True)
    monkeypatch.setattr("alma_bridge.config.settings.operator_allow_mutations", True)

    orchestrator = BridgeOrchestrator()
    request = BridgeRequest(file_path="/tmp/installer.exe")
    attempts = [_failed_attempt(1)]
    session_id = outcomes.new_session("/tmp/installer.exe", "abc", {})

    retry_session = BridgeSessionResult(
        session_id=session_id,
        file_path="/tmp/installer.exe",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        success=True,
        summary="nested ok",
        winning_attempt=_successful_attempt(2),
        attempts=attempts + [_successful_attempt(2)],
    )

    route_result = RouteExecutionResult(
        route_id="route:heal_then_bridge:app.exe",
        kind="heal_then_bridge",
        success=False,
        requires_bridge_retry=True,
        preferred_remediation_id="baseline_retry",
    )

    with patch.object(orchestrator._route_discovery, "discover", return_value={"routes": [{"id": "r1"}]}):
        with patch.object(orchestrator._route_selection, "select", return_value=[{"id": "r1", "kind": "heal_then_bridge"}]):
            with patch.object(orchestrator._route_executor, "execute_route", return_value=route_result):
                with patch.object(orchestrator, "_run_session", return_value=retry_session) as run_session:
                    result = orchestrator._try_auto_compatibility(
                        request=request,
                        session_id=session_id,
                        attempt_records=attempts,
                        hardware={},
                        started_at=datetime.now(timezone.utc),
                        digest="abc",
                        last_recommended=[],
                        rerank_events=[],
                        target_path="/tmp/codeblocks.exe",
                    )

    assert result is not None
    assert result.success is True
    assert "Auto-compatibility succeeded" in result.summary
    run_session.assert_called_once()
    assert run_session.call_args.kwargs["request"].file_path == "/tmp/codeblocks.exe"


def test_bridge_retry_without_strategy_id_still_targets_launcher_path(monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.bridge_auto_remediate", True)
    monkeypatch.setattr("alma_bridge.config.settings.operator_allow_mutations", True)

    orchestrator = BridgeOrchestrator()
    request = BridgeRequest(file_path="/tmp/codeblocks-setup.exe", launch_after_install=True)
    attempts = [_failed_attempt(4, phase="launcher", signature="missing_visual_c_runtime")]
    session_id = outcomes.new_session("/tmp/codeblocks-setup.exe", "abc", {})

    route_result = RouteExecutionResult(
        route_id="route:heal_then_bridge:codeblocks.exe",
        kind="heal_then_bridge",
        success=False,
        requires_bridge_retry=True,
        preferred_remediation_id="baseline_retry",
    )

    with patch.object(orchestrator._route_discovery, "discover", return_value={"routes": [{"id": "r1"}]}):
        with patch.object(orchestrator._route_selection, "select", return_value=[{"id": "r1", "kind": "heal_then_bridge"}]):
            with patch.object(orchestrator._route_executor, "execute_route", return_value=route_result):
                with patch.object(
                    orchestrator,
                    "_run_session",
                    return_value=BridgeSessionResult(
                        session_id=session_id,
                        file_path="/tmp/codeblocks-setup.exe",
                        started_at=datetime.now(timezone.utc),
                        finished_at=datetime.now(timezone.utc),
                        success=False,
                        summary="still failing",
                        attempts=attempts,
                    ),
                ) as run_session:
                    orchestrator._try_auto_compatibility(
                        request=request,
                        session_id=session_id,
                        attempt_records=attempts,
                        hardware={},
                        started_at=datetime.now(timezone.utc),
                        digest="abc",
                        last_recommended=[],
                        rerank_events=[],
                        target_path="/tmp/codeblocks.exe",
                    )

    assert run_session.call_args.kwargs["request"].file_path == "/tmp/codeblocks.exe"


def test_failed_verification_still_allows_next_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.bridge_auto_remediate", False)
    _patch_gui_timeouts(monkeypatch)
    launcher = _wine_gui_exe(tmp_path)
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    orchestrator = BridgeOrchestrator()
    execute_calls = {"n": 0}

    def fake_execute(**kwargs):
        execute_calls["n"] += 1
        return {
            "success": False,
            "exit_code": 1,
            "stdout": "",
            "stderr": "[alma] gui detached",
            "duration_ms": 4,
        }

    monkeypatch.setattr("alma_bridge.learning.orchestrator.execute_attempt", fake_execute)
    _patch_handoff_prereqs(monkeypatch, orchestrator, tmp_path)
    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator.build_execution_plan",
        lambda *args, **kwargs: [
            {"strategy_id": "wine_host", "runtime": "wine", "mode": "host", "command": ["wine", launcher], "env": {}},
        ],
    )
    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator.next_launcher_remediation",
        lambda sig, tried: {"id": "vcrun_fix"} if sig and "vcrun_fix" not in {r for r in tried} else None,
    )

    session_id = outcomes.new_session(launcher, "hash", {})
    lifecycle = SessionLifecycleManager(session_id)
    lifecycle.transition(SessionState.CREATED, reason="t", expected_from=SessionState.CREATED)
    lifecycle.transition(SessionState.INSPECTING, reason="t", expected_from=SessionState.CREATED)
    lifecycle.transition(SessionState.PLANNING, reason="t", expected_from=SessionState.INSPECTING)
    lifecycle.transition(SessionState.POLICY_CHECK, reason="t", expected_from=SessionState.PLANNING)

    def persist_side_effect(**kwargs):
        record = kwargs["record"]
        boundary = kwargs["boundary"]
        passed = record.attempt_number >= 2
        if boundary.error_signature and not passed:
            record.error_signature = boundary.error_signature
        record.success = passed
        return passed, {"passed": passed}

    with patch.object(orchestrator, "_persist_verified_attempt", side_effect=persist_side_effect):
        with patch.object(
            orchestrator._verification_gateway,
            "run",
            side_effect=lambda **kwargs: MagicMock(
                policy_passed=kwargs["record"].attempt_number >= 2,
                verification={"passed": kwargs["record"].attempt_number >= 2},
                error_signature=(
                    "missing_visual_c_runtime"
                    if kwargs["record"].attempt_number < 2
                    else None
                ),
            ),
        ):
            with patch.object(orchestrator, "_persist_profile_candidate_before_success", return_value=None):
                with patch.object(orchestrator, "_promote_profile_candidate_after_success"):
                    with patch(
                        "alma_bridge.learning.orchestrator.declare_verified_session_success",
                    ):
                        result = orchestrator._run_launcher_handoff(
                            request=BridgeRequest(file_path="/tmp/setup.exe", max_attempts=3),
                            session_id=session_id,
                            lifecycle=lifecycle,
                            launcher_path=launcher,
                            wine_prefix=str(prefix),
                            hardware={"architecture": "x86_64"},
                            started_at=datetime.now(timezone.utc),
                            digest="hash",
                            prior_attempts=[],
                            skipped_installer=True,
                        )

    assert result.success is True
    assert execute_calls["n"] == 2
    assert len(result.attempts) == 2
    assert result.attempts[0].success is False
    assert result.attempts[1].success is True


def test_process_launch_without_verification_does_not_stop_retries(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.bridge_auto_remediate", False)
    _patch_gui_timeouts(monkeypatch)
    exe = _wine_gui_exe(tmp_path)
    orchestrator = BridgeOrchestrator()
    execute_calls = {"n": 0}

    def fake_execute(**kwargs):
        execute_calls["n"] += 1
        return {
            "success": True,
            "exit_code": 0,
            "stdout": "",
            "stderr": "[alma] gui detached",
            "duration_ms": 2,
        }

    def fail_wine_gui_verify(result, **kwargs):
        return dict(result), "gui_process_not_found", []

    _patch_run_session_prereqs(monkeypatch, orchestrator, tmp_path)
    monkeypatch.setattr("alma_bridge.learning.orchestrator.execute_attempt", fake_execute)
    monkeypatch.setattr(
        orchestrator._planner,
        "plan",
        lambda *args, **kwargs: _mock_plan(strategies=["wine_host"]),
    )
    monkeypatch.setattr(
        "alma_bridge.execution.wine_gui_handoff.evaluate_wine_gui_launch_result",
        fail_wine_gui_verify,
    )
    monkeypatch.setattr(
        "alma_bridge.execution.wine_gui_handoff.observe_target_gui_process",
        lambda *args, **kwargs: SimpleNamespace(
            appeared=False,
            survived=False,
            to_evidence_lines=lambda: [],
            to_dict=lambda: {},
        ),
    )

    session_id = outcomes.new_session(exe, "hash", {})
    lifecycle = SessionLifecycleManager(session_id)
    lifecycle.transition(SessionState.CREATED, reason="t", expected_from=SessionState.CREATED)
    lifecycle.transition(SessionState.INSPECTING, reason="t", expected_from=SessionState.CREATED)
    lifecycle.transition(SessionState.PLANNING, reason="t", expected_from=SessionState.INSPECTING)

    with patch.object(orchestrator, "_persist_profile_candidate_before_success", return_value=None):
        result = orchestrator._run_session(
            request=BridgeRequest(file_path=exe, max_attempts=2),
            session_id=session_id,
            lifecycle=lifecycle,
            retry_guard=MagicMock(max_attempts=2, session_timed_out=lambda: False, escalation_allowed=lambda _sig: True),
            hardware={"architecture": "x86_64"},
            started_at=datetime.now(timezone.utc),
            digest="hash",
            inspection=SimpleNamespace(recommended_strategy_id="wine_host"),
            cancel_check=None,
        )

    assert result.success is False
    assert execute_calls["n"] >= 2


def test_auto_compat_stops_when_session_already_succeeded(monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.bridge_auto_remediate", True)
    session_id = outcomes.new_session("/tmp/app.exe", "hash", {})
    lifecycle = _setup_succeeded_session(session_id, winning=_successful_attempt(1))
    orchestrator = BridgeOrchestrator()

    with patch.object(orchestrator, "_run_session") as run_session:
        result = orchestrator._try_auto_compatibility(
            request=BridgeRequest(file_path="/tmp/app.exe"),
            session_id=session_id,
            lifecycle=lifecycle,
            attempt_records=[_failed_attempt(1)],
            hardware={},
            started_at=datetime.now(timezone.utc),
            digest="hash",
            last_recommended=[],
            rerank_events=[],
        )

    assert result is not None
    assert result.success is True
    run_session.assert_not_called()


def test_stop_on_success_requires_authoritative_verification():
    session_id = outcomes.new_session("/tmp/app.exe", "hash", {})
    lifecycle = SessionLifecycleManager(session_id)
    orchestrator = BridgeOrchestrator()
    result = orchestrator._return_if_session_succeeded(
        lifecycle=lifecycle,
        session_id=session_id,
        request=BridgeRequest(file_path="/tmp/app.exe"),
        started_at=datetime.now(timezone.utc),
        digest="hash",
        hardware={},
    )
    assert result is None


def test_verified_codeblock_handoff_stops_later_attempts(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.bridge_auto_remediate", False)
    _patch_gui_timeouts(monkeypatch)

    app_dir = tmp_path / "CodeBlocks"
    app_dir.mkdir()
    launcher = app_dir / "codeblocks.exe"
    write_minimal_pe(launcher, subsystem=IMAGE_SUBSYSTEM_WINDOWS_GUI, pe32plus=False)
    (app_dir / "wxmsw32u_gcc_custom.dll").write_bytes(b"MZ")

    fixture_stderr = (
        Path(__file__).parent / "fixtures" / "codeblocks_startup_stderr.txt"
    ).read_text(encoding="utf-8")
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    orchestrator = BridgeOrchestrator()
    execute_calls = {"n": 0}

    def fake_execute(**kwargs):
        execute_calls["n"] += 1
        return {
            "success": True,
            "exit_code": 0,
            "stdout": "",
            "stderr": fixture_stderr,
            "duration_ms": 2,
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
        "alma_bridge.learning.orchestrator._next_wine_gui_launcher_remediation",
        lambda *args, **kwargs: {"id": "should_not_run"},
    )
    monkeypatch.setattr(
        "alma_bridge.execution.wine_gui_handoff.observe_target_gui_process",
        lambda *args, **kwargs: SimpleNamespace(
            appeared=True,
            survived=True,
            to_evidence_lines=lambda: ["target_process=codeblocks.exe"],
            to_dict=lambda: {"pid": 7777},
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
                request=BridgeRequest(file_path="/tmp/setup.exe", max_attempts=5),
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

    assert result.success is True
    assert execute_calls["n"] == 1
    assert outcomes.get_session_state(session_id) == SessionState.SUCCEEDED.value
