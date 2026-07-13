"""Verification authority boundary tests for /bridge/run lifecycle."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from alma_bridge.learning.orchestrator import BridgeOrchestrator, _persist_attempt
from alma_bridge.schemas.models import AttemptRecord, BridgeRequest, ExecutionMode
from alma_bridge.session.lifecycle import InvalidSessionTransition, SessionLifecycleManager
from alma_bridge.session.services.verification import (
    DEFAULT_AGGREGATE_POLICY,
    DEFAULT_POLICY_ID,
    DEFAULT_POLICY_VERSION,
    ExecutionEvidence,
    VerificationCheckResult,
    VerificationResult,
    verification_result_from_exception,
)
from alma_bridge.session.state import SessionState
from alma_bridge.session.verification_gateway import (
    VerificationGateway,
    declare_verified_session_success,
)
from alma_bridge.storage import outcomes


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    outcomes.init_outcome_store()
    yield


def _session() -> str:
    return outcomes.new_session(
        "/tmp/test.exe",
        "hash",
        {"architecture": "x86_64"},
    )


def _mock_verifier(return_value: VerificationResult):
    verifier = MagicMock()
    verifier.verify_execution.return_value = return_value
    return verifier


def _passing_native_verification() -> VerificationResult:
    return VerificationResult(
        passed=True,
        confidence=0.9,
        checks=[
            VerificationCheckResult(
                verifier_id="runner",
                verifier_version="1.0.0",
                check_kind="exit_code_zero",
                passed=True,
                confidence=0.9,
                evidence=["exit_code=0"],
            )
        ],
        evidence=["exit_code=0"],
        success_policy=DEFAULT_AGGREGATE_POLICY,
    )


def _failing_verification(reason: str = "verification_failed") -> VerificationResult:
    return VerificationResult(
        passed=False,
        confidence=0.2,
        checks=[
            VerificationCheckResult(
                verifier_id="runner",
                verifier_version="1.0.0",
                check_kind="exit_code_zero",
                passed=False,
                confidence=0.2,
                evidence=["exit_code=1"],
            )
        ],
        failure_reason=reason,
        error_signature=reason,
        success_policy=DEFAULT_AGGREGATE_POLICY,
    )


class TestVerificationGateway:
    def test_observing_to_verifying_on_eligible_execution(self):
        session_id = _session()
        lifecycle = SessionLifecycleManager(session_id)
        lifecycle.transition(SessionState.CREATED, reason="start")
        lifecycle.transition(SessionState.INSPECTING, reason="inspect")
        lifecycle.transition(SessionState.PLANNING, reason="plan")
        lifecycle.transition(SessionState.POLICY_CHECK, reason="policy")
        lifecycle.transition(SessionState.EXECUTING, reason="exec")

        transitions: list[SessionState] = []

        def _track(lifecycle_mgr, state, **kwargs):
            lifecycle_mgr.transition(state, reason=kwargs.get("reason", "test"))

        gateway = VerificationGateway(
            _mock_verifier(_passing_native_verification()),
            transition=_track,
        )
        record = AttemptRecord(
            attempt_number=1,
            strategy_id="native_host",
            remediation_id=None,
            runtime="native",
            command=["/tmp/test.sh"],
            env={},
            mode=ExecutionMode.HOST,
            success=False,
            exit_code=0,
            duration_ms=1,
            phase="native",
        )
        evidence = ExecutionEvidence(
            session_id=session_id,
            attempt_number=1,
            phase="native",
            result={"success": True, "exit_code": 0},
            file_path="/tmp/test.sh",
        )
        result = gateway.run(lifecycle=lifecycle, evidence=evidence, record=record)
        assert result.policy_passed is True
        assert lifecycle.state == SessionState.VERIFYING
        assert record.success is False  # gateway does not set success

    def test_classifying_on_clear_execution_failure(self):
        session_id = _session()
        lifecycle = SessionLifecycleManager(session_id)
        for state in (
            SessionState.CREATED,
            SessionState.INSPECTING,
            SessionState.PLANNING,
            SessionState.POLICY_CHECK,
            SessionState.EXECUTING,
        ):
            lifecycle.transition(state, reason="advance")

        gateway = VerificationGateway(
            _mock_verifier(_failing_verification()),
            transition=lambda lc, st, **kw: lc.transition(st, reason=kw.get("reason", "t")),
        )
        record = AttemptRecord(
            attempt_number=1,
            strategy_id="native_host",
            remediation_id=None,
            runtime="native",
            command=["/tmp/test.sh"],
            env={},
            mode=ExecutionMode.HOST,
            success=False,
            exit_code=1,
            duration_ms=1,
            phase="native",
        )
        evidence = ExecutionEvidence(
            session_id=session_id,
            attempt_number=1,
            phase="native",
            result={"success": False, "exit_code": 1, "error_signature": "unknown_error"},
            file_path="/tmp/test.sh",
        )
        result = gateway.run(lifecycle=lifecycle, evidence=evidence, record=record)
        assert result.policy_passed is False
        assert lifecycle.state == SessionState.CLASSIFYING

    def test_succeeded_only_from_verifying(self):
        session_id = _session()
        lifecycle = SessionLifecycleManager(session_id)
        for state in (
            SessionState.CREATED,
            SessionState.INSPECTING,
            SessionState.PLANNING,
            SessionState.POLICY_CHECK,
            SessionState.EXECUTING,
            SessionState.OBSERVING,
            SessionState.VERIFYING,
        ):
            lifecycle.transition(state, reason="advance")

        declare_verified_session_success(
            lifecycle=lifecycle,
            session_id=session_id,
            transition=lambda lc, st, **kw: lc.transition(st, reason=kw.get("reason", "t")),
            summary="verified ok",
        )
        assert lifecycle.state == SessionState.SUCCEEDED
        row = outcomes.get_session(session_id)
        assert row is not None
        assert row["success"] == 1

    def test_cannot_succeed_without_verifying_origin(self):
        session_id = _session()
        lifecycle = SessionLifecycleManager(session_id)
        lifecycle.transition(SessionState.CREATED, reason="start")
        lifecycle.transition(SessionState.INSPECTING, reason="inspect")
        lifecycle.transition(SessionState.PLANNING, reason="plan")
        lifecycle.transition(SessionState.POLICY_CHECK, reason="policy")
        lifecycle.transition(SessionState.EXECUTING, reason="exec")
        with pytest.raises(InvalidSessionTransition):
            declare_verified_session_success(
                lifecycle=lifecycle,
                session_id=session_id,
                transition=lambda lc, st, **kw: lc.transition(st, reason=kw.get("reason", "t")),
                summary="illegal",
            )


class TestOrchestratorVerificationAuthority:
    def _run_native(
        self,
        tmp_path: Path,
        monkeypatch,
        *,
        execute_result: Dict[str, Any],
        verification_result: VerificationResult,
        persist_raises: bool = False,
    ):
        script = tmp_path / "ok.sh"
        script.write_text("#!/bin/sh\nexit 0\n")
        script.chmod(0o755)

        verifier = _mock_verifier(verification_result)
        orch = BridgeOrchestrator(verifier=verifier)

        monkeypatch.setattr(
            "alma_bridge.learning.orchestrator.execute_attempt",
            lambda **kwargs: dict(execute_result),
        )
        if persist_raises:
            monkeypatch.setattr(
                "alma_bridge.learning.orchestrator._persist_attempt",
                lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("persist failed")),
            )

        request = BridgeRequest(file_path=str(script), max_attempts=1, auto_remediate=False)
        return orch.run(request)

    def test_exit_code_zero_cannot_directly_produce_succeeded(self, tmp_path, monkeypatch):
        """Raw exit 0 with failing verification must not reach SUCCEEDED."""
        result = self._run_native(
            tmp_path,
            monkeypatch,
            execute_result={"success": True, "exit_code": 0, "duration_ms": 1, "stdout": "", "stderr": ""},
            verification_result=_failing_verification("exit_code_not_authoritative"),
        )
        assert result.success is False
        transitions = outcomes.list_session_transitions(result.session_id)
        states = [t["next_state"] for t in transitions]
        assert SessionState.SUCCEEDED.value not in states

    def test_verification_engine_exception_cannot_produce_succeeded(self, tmp_path, monkeypatch):
        script = tmp_path / "exc.sh"
        script.write_text("#!/bin/sh\nexit 0\n")
        script.chmod(0o755)
        verifier = MagicMock()
        verifier.verify_execution.side_effect = RuntimeError("engine blew up")
        orch = BridgeOrchestrator(verifier=verifier)
        monkeypatch.setattr(
            "alma_bridge.learning.orchestrator.execute_attempt",
            lambda **kwargs: {"success": True, "exit_code": 0, "duration_ms": 1, "stdout": "", "stderr": ""},
        )
        result = orch.run(BridgeRequest(file_path=str(script), max_attempts=1, auto_remediate=False))
        assert result.success is False

    def test_verification_persistence_failure_cannot_produce_succeeded(self, tmp_path, monkeypatch):
        result = self._run_native(
            tmp_path,
            monkeypatch,
            execute_result={"success": True, "exit_code": 0, "duration_ms": 1, "stdout": "", "stderr": ""},
            verification_result=_passing_native_verification(),
            persist_raises=True,
        )
        assert result.success is False

    def test_successful_attempt_has_persisted_verification_json(self, tmp_path, monkeypatch):
        result = self._run_native(
            tmp_path,
            monkeypatch,
            execute_result={"success": True, "exit_code": 0, "duration_ms": 1, "stdout": "", "stderr": ""},
            verification_result=_passing_native_verification(),
        )
        assert result.success is True
        session = outcomes.get_session(result.session_id)
        assert session is not None
        winning = session["winning_attempt"]
        assert winning is not None
        verification = winning.get("verification") or {}
        assert verification.get("passed") is True
        assert verification.get("success_policy", {}).get("policy_id") == DEFAULT_POLICY_ID
        assert verification.get("success_policy", {}).get("policy_version") == DEFAULT_POLICY_VERSION

    def test_every_check_has_verifier_provenance(self, tmp_path, monkeypatch):
        result = self._run_native(
            tmp_path,
            monkeypatch,
            execute_result={"success": True, "exit_code": 0, "duration_ms": 1, "stdout": "", "stderr": ""},
            verification_result=_passing_native_verification(),
        )
        session = outcomes.get_session(result.session_id)
        checks = (session["winning_attempt"]["verification"].get("checks") or [])
        assert checks
        for check in checks:
            assert check["verifier_id"]
            assert check["verifier_version"]
            assert check["check_kind"]
            assert "passed" in check
            assert "confidence" in check
            assert "timestamp" in check

    def test_succeeded_transition_origin_is_verifying(self, tmp_path, monkeypatch):
        result = self._run_native(
            tmp_path,
            monkeypatch,
            execute_result={"success": True, "exit_code": 0, "duration_ms": 1, "stdout": "", "stderr": ""},
            verification_result=_passing_native_verification(),
        )
        transitions = outcomes.list_session_transitions(result.session_id)
        succeeded = [t for t in transitions if t["next_state"] == SessionState.SUCCEEDED.value]
        assert len(succeeded) == 1
        assert succeeded[0]["previous_state"] == SessionState.VERIFYING.value

    def test_detached_process_without_verification_fails(self, tmp_path, monkeypatch):
        """Detached launcher marker alone must not produce SUCCEEDED."""
        verification = VerificationResult(
            passed=False,
            confidence=0.5,
            checks=[
                VerificationCheckResult(
                    verifier_id="runner",
                    verifier_version="1.0.0",
                    check_kind="process_starts",
                    passed=False,
                    confidence=0.5,
                    evidence=["pending detach"],
                )
            ],
            failure_reason="pending_detach",
            success_policy=DEFAULT_AGGREGATE_POLICY,
        )
        result = self._run_native(
            tmp_path,
            monkeypatch,
            execute_result={
                "success": True,
                "exit_code": 0,
                "duration_ms": 1,
                "stdout": "",
                "stderr": "[alma] launcher detached",
            },
            verification_result=verification,
        )
        assert result.success is False

    def test_installer_discovery_alone_cannot_produce_succeeded(self, tmp_path):
        """Installer exit 0 with failed prefix verification must not pass policy."""
        session_id = _session()
        lifecycle = SessionLifecycleManager(session_id)
        for state in (
            SessionState.CREATED,
            SessionState.INSPECTING,
            SessionState.PLANNING,
            SessionState.POLICY_CHECK,
            SessionState.EXECUTING,
        ):
            lifecycle.transition(state, reason="advance")

        verifier = _mock_verifier(
            VerificationResult(
                passed=False,
                confidence=0.2,
                checks=[
                    VerificationCheckResult(
                        verifier_id="installer_verify",
                        verifier_version="1.0.0",
                        check_kind="prefix_has_launcher",
                        passed=False,
                        confidence=0.2,
                        evidence=["no launcher discovered"],
                    )
                ],
                failure_reason="installer_not_verified",
                error_signature="installer_not_verified",
                success_policy=DEFAULT_AGGREGATE_POLICY,
            )
        )
        gateway = VerificationGateway(
            verifier,
            transition=lambda lc, st, **kw: lc.transition(st, reason=kw.get("reason", "t")),
        )
        record = AttemptRecord(
            attempt_number=1,
            strategy_id="wine_host",
            remediation_id=None,
            runtime="wine",
            command=["wine", "setup.exe"],
            env={},
            mode=ExecutionMode.HOST,
            success=False,
            exit_code=0,
            duration_ms=100,
            phase="install",
        )
        evidence = ExecutionEvidence(
            session_id=session_id,
            attempt_number=1,
            phase="install",
            result={"success": True, "exit_code": 0, "duration_ms": 100},
            file_path=str(tmp_path / "setup.exe"),
            installer=True,
        )
        boundary = gateway.run(lifecycle=lifecycle, evidence=evidence, record=record)
        assert boundary.policy_passed is False
        assert lifecycle.state == SessionState.CLASSIFYING

    def test_prior_success_fast_path_still_requires_verification(self, tmp_path, monkeypatch):
        """Fast-path launcher reuse must still invoke VerificationEngine."""
        launcher = tmp_path / "Launcher.exe"
        launcher.write_bytes(b"MZ")
        prefix = tmp_path / "prefix"
        (prefix / "drive_c").mkdir(parents=True)

        verifier = _mock_verifier(_failing_verification("prior_not_authoritative"))
        orch = BridgeOrchestrator(verifier=verifier)

        monkeypatch.setattr(
            "alma_bridge.learning.orchestrator.classify_program_kind",
            lambda *args, **kwargs: {
                "is_installer": True,
                "is_electron": True,
                "needs_wine": True,
                "needs_gui": True,
            },
        )
        monkeypatch.setattr(
            "alma_bridge.learning.orchestrator._ensure_prefix_runtimes",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            "alma_bridge.learning.orchestrator.require_wine_windows_version",
            lambda *args, **kwargs: (True, ""),
        )
        monkeypatch.setattr(
            "alma_bridge.learning.orchestrator.prepare_electron_wine",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            "alma_bridge.learning.orchestrator.apply_electron_remediation_shims",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            "alma_bridge.learning.orchestrator.run_winetricks",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            "alma_bridge.learning.orchestrator.launcher_ready_for_handoff",
            lambda *args, **kwargs: str(launcher),
        )
        monkeypatch.setattr(
            "alma_bridge.learning.orchestrator.build_execution_plan",
            lambda *args, **kwargs: [
                {
                    "strategy_id": "wine_host",
                    "runtime": "wine",
                    "mode": "host",
                    "command": ["wine", str(launcher)],
                    "env": {"WINEPREFIX": str(prefix)},
                }
            ],
        )
        monkeypatch.setattr(
            "alma_bridge.learning.orchestrator._baseline_launcher_remediation",
            lambda: {"id": None, "env": {}, "args": [], "shims": []},
        )
        monkeypatch.setattr(
            "alma_bridge.learning.orchestrator.next_launcher_remediation",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            "alma_bridge.learning.orchestrator.snapshot_wine_pids",
            lambda *args, **kwargs: [],
        )
        monkeypatch.setattr(
            "alma_bridge.learning.orchestrator.execute_attempt",
            lambda **kwargs: {"success": True, "exit_code": 0, "duration_ms": 1, "stdout": "", "stderr": ""},
        )
        monkeypatch.setattr(
            "alma_bridge.learning.orchestrator.prepare_sudo",
            lambda **kwargs: (True, ""),
        )

        installer = tmp_path / "setup.exe"
        installer.write_bytes(b"MZ" + b"\x00" * 100)
        result = orch.run(
            BridgeRequest(
                file_path=str(installer),
                max_attempts=1,
                launch_after_install=True,
                wine_prefix=str(prefix),
                auto_remediate=False,
            )
        )
        assert result.success is False
        verifier.verify_execution.assert_called()


class TestAggregatePolicy:
    def test_policy_fields_present(self):
        policy = DEFAULT_AGGREGATE_POLICY
        assert policy.policy_id == DEFAULT_POLICY_ID
        assert policy.policy_version == DEFAULT_POLICY_VERSION
        assert "native" in policy.required_checks
        assert policy.contradictory_evidence_behavior == "fail_closed"

    def test_exception_result_has_provenance(self):
        result = verification_result_from_exception(ValueError("boom"))
        assert result.passed is False
        assert result.checks[0].verifier_id == "verification_engine"
        assert result.verifier_exception == "boom"


class TestNonOrchestratorSuccessPaths:
    def test_route_execution_success_does_not_finalize_session(self, tmp_path, monkeypatch):
        from alma_bridge.session.services.routes import DefaultRouteExecutionService, RouteExecutionContext

        session_id = _session()
        monkeypatch.setattr(
            "alma_bridge.execution.preflight.apply_ml_wine_fix",
            lambda *args, **kwargs: {"actions": ["installed dotnet"]},
        )
        monkeypatch.setattr(
            "alma_bridge.hardware.prefixes.find_best_prefix",
            lambda *args, **kwargs: str(tmp_path / "prefix"),
        )
        svc = DefaultRouteExecutionService()
        ctx = RouteExecutionContext(
            session_id=session_id,
            correlation_id=session_id,
            file_path="/tmp/app.exe",
            wine_prefix=str(tmp_path / "prefix"),
            error_text="dotnet missing",
            bridge_signature="dotnet_missing",
            preferred_remediation_id=None,
        )
        route = {"id": "prefix_bootstrap", "kind": "wine_prefix_bootstrap", "file_path": "/tmp/app.exe"}
        discovery = {"bridge_signature": "dotnet_missing", "file_path": "/tmp/app.exe"}
        result = svc.execute_route(route, discovery, ctx, apply=True, allow_host_mutations=True)
        assert result.success is True
        session = outcomes.get_session(session_id)
        assert session["finished_at"] is None
        assert session["success"] == 0

    def test_remediation_outcome_alone_not_session_success(self):
        """AttemptRecord.success is only set by orchestrator after verification."""
        record = AttemptRecord(
            attempt_number=1,
            strategy_id="wine_host",
            remediation_id="software_rendering",
            runtime="wine",
            command=["wine"],
            env={},
            mode=ExecutionMode.HOST,
            success=False,
            duration_ms=1,
            phase="install",
        )
        assert record.success is False
