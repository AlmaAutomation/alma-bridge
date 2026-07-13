"""Permanent architectural invariant tests for the authoritative bridge lifecycle."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from alma_bridge.learning.orchestrator import BridgeOrchestrator
from alma_bridge.schemas.models import BridgeRequest
from alma_bridge.session.mutations import run_prefix_mutation
from alma_bridge.session.policy import ActionIntent, ActionType, ExecutionScope, MutationScope, PolicyGate
from alma_bridge.session.state import SessionState
from alma_bridge.session.verification_gateway import declare_verified_session_success
from alma_bridge.storage import outcomes


ROOT = Path(__file__).resolve().parents[1]
ALMA_BRIDGE = ROOT / "alma_bridge"
SESSION_SERVICES = ALMA_BRIDGE / "session" / "services"


def _py_files_under(path: Path) -> list[Path]:
    return sorted(p for p in path.rglob("*.py") if p.is_file())


def _imports_orchestrator(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and "orchestrator" in node.module:
            return True
        if isinstance(node, ast.Import):
            if any("orchestrator" in alias.name for alias in node.names):
                return True
    return False


def _calls_finalize_success_true(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = None
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name != "finalize_session":
            continue
        for kw in node.keywords:
            if kw.arg == "success" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                hits.append(f"{path.relative_to(ROOT)}")
                break
        if node.args and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and node.args[1].value is True:
            hits.append(f"{path.relative_to(ROOT)}")
    return hits


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    outcomes.init_outcome_store()
    yield


class TestStaticInvariants:
    def test_route_services_do_not_import_orchestrator(self):
        offenders = [str(p) for p in _py_files_under(SESSION_SERVICES) if _imports_orchestrator(p)]
        assert offenders == []

    def test_only_verification_gateway_finalizes_success_true(self):
        allowed = {ALMA_BRIDGE / "session" / "verification_gateway.py"}
        offenders: list[str] = []
        for path in _py_files_under(ALMA_BRIDGE):
            if path in allowed:
                continue
            if path.name.startswith("profile_shadow"):
                continue
            offenders.extend(_calls_finalize_success_true(path))
        assert offenders == []

    def test_orchestrator_is_only_production_lifecycle_driver(self):
        """SessionLifecycleManager must not be constructed in route/operator services."""
        forbidden_roots = (
            ALMA_BRIDGE / "session" / "services",
            ALMA_BRIDGE / "operator",
            ALMA_BRIDGE / "api",
        )
        offenders: list[str] = []
        for root in forbidden_roots:
            for path in _py_files_under(root):
                if "SessionLifecycleManager(" in path.read_text(encoding="utf-8"):
                    offenders.append(str(path.relative_to(ROOT)))
        assert offenders == []

    def test_prefix_mutations_require_policy_and_lock(self):
        source = inspect.getsource(run_prefix_mutation)
        assert "policy.evaluate" in source
        assert "prefix_lock" in source


class TestBehavioralInvariants:
    def test_only_verification_gateway_may_reach_succeeded(self, tmp_path, monkeypatch):
        script = tmp_path / "ok.sh"
        script.write_text("#!/bin/sh\nexit 0\n")
        script.chmod(0o755)
        monkeypatch.setattr(
            "alma_bridge.learning.orchestrator.execute_attempt",
            lambda **kwargs: {
                "success": True,
                "exit_code": 0,
                "duration_ms": 1,
                "stdout": "",
                "stderr": "",
            },
        )
        result = BridgeOrchestrator().run(
            BridgeRequest(file_path=str(script), max_attempts=1, auto_remediate=False)
        )
        transitions = outcomes.list_session_transitions(result.session_id)
        succeeded = [t for t in transitions if t["next_state"] == SessionState.SUCCEEDED.value]
        assert len(succeeded) == 1
        assert succeeded[0]["previous_state"] == SessionState.VERIFYING.value

    def test_succeeded_session_has_verification_json(self, tmp_path, monkeypatch):
        script = tmp_path / "ok.sh"
        script.write_text("#!/bin/sh\nexit 0\n")
        script.chmod(0o755)
        monkeypatch.setattr(
            "alma_bridge.learning.orchestrator.execute_attempt",
            lambda **kwargs: {
                "success": True,
                "exit_code": 0,
                "duration_ms": 1,
                "stdout": "",
                "stderr": "",
            },
        )
        result = BridgeOrchestrator().run(
            BridgeRequest(file_path=str(script), max_attempts=1, auto_remediate=False)
        )
        session = outcomes.get_session(result.session_id)
        assert session is not None
        winning = session["winning_attempt"]
        assert winning is not None
        assert winning.get("verification", {}).get("passed") is True

    def test_illegal_succeeded_without_verifying_origin(self):
        session_id = outcomes.new_session("/tmp/a", "h", {})
        from alma_bridge.session.lifecycle import InvalidSessionTransition, SessionLifecycleManager

        lifecycle = SessionLifecycleManager(session_id)
        for state in (
            SessionState.CREATED,
            SessionState.INSPECTING,
            SessionState.PLANNING,
            SessionState.POLICY_CHECK,
            SessionState.EXECUTING,
            SessionState.OBSERVING,
        ):
            lifecycle.transition(state, reason="advance")
        with pytest.raises(InvalidSessionTransition):
            declare_verified_session_success(
                lifecycle=lifecycle,
                session_id=session_id,
                transition=lambda lc, st, **kw: lc.transition(st, reason=kw.get("reason", "t")),
                summary="illegal",
            )

    def test_route_success_does_not_finalize_session(self, tmp_path, monkeypatch):
        from alma_bridge.session.services.routes import DefaultRouteExecutionService, RouteExecutionContext

        session_id = outcomes.new_session("/tmp/app.exe", "hash", {})
        monkeypatch.setattr(
            "alma_bridge.execution.preflight.apply_ml_wine_fix",
            lambda *args, **kwargs: {"actions": ["ok"]},
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
        route = {"id": "bootstrap", "kind": "wine_prefix_bootstrap", "file_path": "/tmp/app.exe"}
        discovery = {"bridge_signature": "dotnet_missing", "file_path": "/tmp/app.exe"}
        out = svc.execute_route(route, discovery, ctx, apply=True, allow_host_mutations=True)
        assert out.success is True
        row = outcomes.get_session(session_id)
        assert row["finished_at"] is None
        assert row["success"] == 0

    def test_prefix_mutation_blocks_without_policy_approval(self, tmp_path, monkeypatch):
        monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
        called = {"ran": False}

        def _fn():
            called["ran"] = True
            return "done"

        intent = ActionIntent(
            action_id="blocked",
            action_type=ActionType.PREFLIGHT,
            mutation_scope=MutationScope.WINE_PREFIX,
            execution_scope=ExecutionScope.BRIDGE_SESSION,
            risk="high",
            actor="test",
            session_id="sess",
            correlation_id="sess",
            target_resource=str(tmp_path / "prefix"),
            prefix_key=str(tmp_path / "prefix"),
            auto_remediate_requested=False,
        )
        gate = PolicyGate()
        decision, result, error = run_prefix_mutation(intent, gate, _fn)
        assert decision is not None
        assert decision.allowed is False
        assert result is None
        assert called["ran"] is False
