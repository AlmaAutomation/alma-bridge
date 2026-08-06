"""Tests for the official Alma CLI."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from alma_bridge.cli import alma_app, handlers
from alma_bridge.runtime_intelligence.models import CorpusKind
from alma_bridge.schemas.models import AttemptRecord, BridgeSessionResult, ExecutionMode
from alma_bridge.storage.outcomes import finalize_session, init_outcome_store, new_session, record_attempt


runner = CliRunner()


@pytest.fixture
def hello64_path():
    from tests.compatibility_intelligence.conftest import FIXTURES

    path = FIXTURES / "hello64.exe"
    if not path.is_file():
        pytest.skip("native_runtime fixtures not built")
    return path


@pytest.fixture
def spaced_exe_path(tmp_path, hello64_path):
    target = tmp_path / "my app.exe"
    target.write_bytes(hello64_path.read_bytes())
    return target


@pytest.fixture
def outcome_store(tmp_path, monkeypatch):
    from alma_bridge.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "db_path", tmp_path / "outcomes.db")
    init_outcome_store()
    return tmp_path / "outcomes.db"


def _parse_json_stdout(result) -> dict:
    assert result.stdout.strip(), "expected JSON stdout"
    return json.loads(result.stdout)


def _assert_no_rich_codes(text: str) -> None:
    assert "\x1b[" not in text


COMMANDS_WITH_JSON = (
    (["version"], {}),
    (["providers"], {}),
)


class TestAlmaCliPackaging:
    def test_installed_entry_point(self):
        alma_path = shutil.which("alma")
        if alma_path is None:
            pytest.skip("alma not installed on PATH")
        proc = subprocess.run(["alma", "version"], capture_output=True, text=True, check=False)
        assert proc.returncode == 0
        assert "alma-bridge" in proc.stdout or "Alma" in proc.stdout

    def test_help_lists_all_commands(self):
        result = runner.invoke(alma_app.app, ["--help"])
        assert result.exit_code == 0
        for command in (
            "analyze",
            "predict",
            "inspect",
            "run",
            "verify",
            "report",
            "providers",
            "version",
        ):
            assert command in result.stdout
        assert "--json" in result.stdout


class TestAlmaCliJsonMode:
    def test_version_json_stdout_only(self):
        result = runner.invoke(alma_app.app, ["--json", "version"])
        assert result.exit_code == 0
        _assert_no_rich_codes(result.stdout)
        payload = _parse_json_stdout(result)
        assert payload["ok"] is True
        assert payload["command"] == "version"
        assert payload["data"]["package"] == "alma-bridge"

    def test_providers_json(self):
        result = runner.invoke(alma_app.app, ["--json", "providers"])
        assert result.exit_code == 0
        _assert_no_rich_codes(result.stdout)
        payload = _parse_json_stdout(result)
        providers = payload["data"]["providers"]
        assert any(p["provider_id"] == "wine" for p in providers)

    def test_analyze_json(self, hello64_path):
        result = runner.invoke(alma_app.app, ["--json", "analyze", str(hello64_path)])
        assert result.exit_code == 0
        payload = _parse_json_stdout(result)
        assert payload["data"]["binary_digest"]
        assert payload["data"]["read_only"] is True

    def test_predict_json_non_authoritative(self, hello64_path):
        result = runner.invoke(alma_app.app, ["--json", "predict", str(hello64_path)])
        assert result.exit_code == 0
        payload = _parse_json_stdout(result)
        assert payload["data"]["authority"] == "non_authoritative_prediction"
        assert payload["data"]["disclaimer"]

    def test_inspect_json(self, hello64_path):
        result = runner.invoke(alma_app.app, ["--json", "inspect", str(hello64_path)])
        assert result.exit_code == 0
        payload = _parse_json_stdout(result)
        assert payload["data"]["imports"]

    @patch("alma_bridge.cli.handlers._orchestrator")
    def test_run_json(self, mock_orchestrator_factory, hello64_path):
        orchestrator = MagicMock()
        mock_orchestrator_factory.return_value = orchestrator
        orchestrator.run.return_value = BridgeSessionResult(
            session_id="sess-json",
            file_path=str(hello64_path),
            file_hash="abc",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            success=True,
            summary="ok",
            attempts=[],
        )
        result = runner.invoke(alma_app.app, ["--json", "run", str(hello64_path)])
        assert result.exit_code == 0
        payload = _parse_json_stdout(result)
        assert payload["data"]["session_id"] == "sess-json"
        assert payload["data"]["delegated_to"] == "BridgeOrchestrator"

    def test_missing_file_json_error_on_stdout_and_stderr(self):
        result = runner.invoke(alma_app.app, ["--json", "analyze", "/no/such/file.exe"])
        assert result.exit_code == 1
        payload = _parse_json_stdout(result)
        assert payload["ok"] is False
        assert payload["command"] == "analyze"
        assert result.stderr.strip()

    def test_missing_session_json(self, outcome_store):
        result = runner.invoke(alma_app.app, ["--json", "verify", "missing-session"])
        assert result.exit_code == 1
        payload = _parse_json_stdout(result)
        assert payload["ok"] is False
        assert payload["code"] == "session_not_found"


class TestAlmaCliCommands:
    def test_version_renders(self):
        result = runner.invoke(alma_app.app, ["version"])
        assert result.exit_code == 0
        assert "Alma" in result.stdout
        assert "alma-bridge" in result.stdout

    def test_analyze_missing_file(self):
        result = runner.invoke(alma_app.app, ["analyze", "/no/such/binary.exe"])
        assert result.exit_code == 1

    def test_analyze_shows_full_digest(self, hello64_path):
        result = runner.invoke(alma_app.app, ["analyze", str(hello64_path)])
        assert result.exit_code == 0
        analysis = handlers.analyze_executable(str(hello64_path), persist=False)
        assert analysis.binary_digest in result.stdout

    def test_analyze_path_with_spaces(self, spaced_exe_path):
        result = runner.invoke(alma_app.app, ["analyze", str(spaced_exe_path)])
        assert result.exit_code == 0

    def test_predict_labels_non_authoritative(self, hello64_path):
        result = runner.invoke(alma_app.app, ["predict", str(hello64_path)])
        assert result.exit_code == 0
        assert "Non-authoritative" in result.stdout

    def test_inspect_hello64(self, hello64_path):
        result = runner.invoke(alma_app.app, ["inspect", str(hello64_path)])
        assert result.exit_code == 0
        assert "Inspect" in result.stdout

    def test_verify_with_stored_evidence(self, outcome_store):
        session_id = new_session("/tmp/app.exe", "digest123", {})
        record_attempt(
            session_id=session_id,
            attempt_number=1,
            strategy_id="native_alma_console",
            remediation_id=None,
            runtime="native",
            command=["/tmp/app.exe"],
            env={},
            mode="host",
            success=True,
            exit_code=0,
            error_signature=None,
            detected_error=None,
            stdout="",
            stderr="",
            duration_ms=10,
            verification={"passed": True, "confidence": 0.9, "checks": []},
        )
        finalize_session(session_id, success=True, summary="verified")
        result = runner.invoke(alma_app.app, ["verify", session_id])
        assert result.exit_code == 0
        assert "verified" in result.stdout.lower()

    def test_verify_unverifiable(self, outcome_store):
        session_id = new_session("/tmp/app.exe", "digest123", {})
        finalize_session(session_id, success=False, summary="no verification")
        result = runner.invoke(alma_app.app, ["verify", session_id])
        assert result.exit_code == 0
        assert "unverifiable" in result.stdout.lower()

    def test_report_unenrolled_session_does_not_borrow_corpus(self, outcome_store):
        session_id = new_session("/tmp/unenrolled.exe", "not-in-any-corpus-digest", {})
        finalize_session(session_id, success=False, summary="failed")
        payload = handlers.report_session(session_id, corpus=CorpusKind.REAL_WORLD)
        assert payload["corpus_enrollment_status"] == "not_enrolled"
        assert payload["compatibility_index"]["status"] == "insufficient_evidence"
        assert payload["compatibility_index"]["index_value"] is None
        result = runner.invoke(
            alma_app.app,
            ["--json", "report", session_id, "--corpus", "real_world"],
        )
        assert result.exit_code == 0
        body = _parse_json_stdout(result)
        assert body["data"]["corpus_enrollment_status"] == "not_enrolled"

    @patch("alma_bridge.cli.handlers._orchestrator")
    def test_run_delegates_to_orchestrator_only(self, mock_orchestrator_factory, hello64_path):
        orchestrator = MagicMock()
        mock_orchestrator_factory.return_value = orchestrator
        orchestrator.run.return_value = BridgeSessionResult(
            session_id="sess-cli-1",
            file_path=str(hello64_path),
            file_hash="abc",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            success=True,
            summary="ok",
            attempts=[
                AttemptRecord(
                    attempt_number=1,
                    strategy_id="native_alma_console",
                    runtime="native",
                    command=[str(hello64_path)],
                    mode=ExecutionMode.HOST,
                    success=True,
                    exit_code=0,
                )
            ],
        )
        result = runner.invoke(alma_app.app, ["run", str(hello64_path)])
        assert result.exit_code == 0
        orchestrator.run.assert_called_once()
        assert "sess-cli-1" in result.stdout

    @patch("alma_bridge.cli.handlers._orchestrator")
    def test_run_failure_exit_code(self, mock_orchestrator_factory, hello64_path):
        orchestrator = MagicMock()
        mock_orchestrator_factory.return_value = orchestrator
        orchestrator.run.return_value = BridgeSessionResult(
            session_id="sess-cli-2",
            file_path=str(hello64_path),
            file_hash="abc",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            success=False,
            summary="failed",
            attempts=[],
        )
        result = runner.invoke(alma_app.app, ["run", str(hello64_path)])
        assert result.exit_code == 2

    @patch("alma_bridge.cli.handlers._orchestrator")
    def test_run_includes_runtime_feature_flags(self, mock_orchestrator_factory, hello64_path, monkeypatch):
        from alma_bridge.config import settings

        monkeypatch.setattr(settings, "native_runtime_enabled", False)
        monkeypatch.setattr(settings, "allow_experimental_runtimes", False)
        orchestrator = MagicMock()
        mock_orchestrator_factory.return_value = orchestrator
        orchestrator.run.return_value = BridgeSessionResult(
            session_id="sess-gates",
            file_path=str(hello64_path),
            file_hash="abc",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            success=False,
            summary="blocked",
            attempts=[],
        )
        result = runner.invoke(alma_app.app, ["--json", "run", str(hello64_path)])
        payload = _parse_json_stdout(result)
        assert payload["data"]["runtime_flags"]["native_runtime_enabled"] is False

    def test_keyboard_interrupt_exit_code(self):
        def _raise_interrupt():
            raise KeyboardInterrupt

        with patch("alma_bridge.cli.alma_app.handlers.list_providers", side_effect=_raise_interrupt):
            result = runner.invoke(alma_app.app, ["providers"])
        assert result.exit_code == 130


class TestAlmaCliHandlers:
    def test_resolve_path_absolute(self, hello64_path):
        resolved = handlers.resolve_executable_path(str(hello64_path))
        assert Path(resolved).is_absolute()

    def test_predict_snapshot_persist_explicit(self, hello64_path, tmp_path, monkeypatch):
        from alma_bridge.config import settings

        monkeypatch.setattr(settings, "data_dir", tmp_path)
        payload = handlers.predict_executable(str(hello64_path), persist=True)
        assert payload["snapshot_persisted"] is True
        assert payload.get("snapshot_id")


class TestAlmaCliBoundaries:
    FORBIDDEN_COMMANDS = ("certify", "promote", "govern", "remediate", "execute-policy")

    def test_no_forbidden_top_level_commands(self):
        result = runner.invoke(alma_app.app, ["--help"])
        lowered = result.stdout.lower()
        for forbidden in self.FORBIDDEN_COMMANDS:
            assert forbidden not in lowered

    def test_handlers_do_not_import_operator(self):
        import alma_bridge.cli.handlers as handler_module

        text = Path(handler_module.__file__).read_text(encoding="utf-8")
        assert "operator_loop" not in text
        assert "ActionIntent" not in text
