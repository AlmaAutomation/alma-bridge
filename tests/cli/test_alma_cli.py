"""Tests for the official Alma CLI."""

from __future__ import annotations

import importlib.metadata
import json
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from alma_bridge.cli import alma_app, handlers
from alma_bridge.cli.provider_decision import resolve_provider_decision
from alma_bridge.compatibility_intelligence.models import (
    ACI_SCHEMA_VERSION,
    CapabilityRequirement,
    CompatibilityAnalysisResult,
    CompatibilityGraph,
    CompatibilityPrediction,
    ConfidenceAssessment,
    ConfidenceLevelName,
    CoverageReport,
    PeAnalysisMetadata,
    ProviderCoverageBreakdown,
    ProvenanceEvidence,
)
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


def _installed_alma_bin() -> Path | None:
    alma_bin = Path(sys.executable).parent / "alma"
    if not alma_bin.is_file():
        return None
    try:
        importlib.metadata.distribution("alma-bridge")
    except importlib.metadata.PackageNotFoundError:
        return None
    return alma_bin


class TestAlmaCliPackaging:
    def test_pyproject_declares_alma_entry_point(self):
        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        with pyproject.open("rb") as handle:
            scripts = tomllib.load(handle)["project"]["scripts"]
        assert scripts["alma"] == "alma_bridge.cli.alma_app:main"

    def test_package_metadata_exposes_alma_console_script(self):
        try:
            dist = importlib.metadata.distribution("alma-bridge")
        except importlib.metadata.PackageNotFoundError:
            pytest.skip("alma-bridge package not installed in active interpreter")
        entry_points = {
            ep.name: ep.value
            for ep in dist.entry_points
            if ep.group == "console_scripts"
        }
        assert entry_points.get("alma") == "alma_bridge.cli.alma_app:main"

    def test_installed_entry_point(self):
        alma_bin = _installed_alma_bin()
        if alma_bin is None:
            pytest.skip(
                "alma console script missing under active interpreter "
                f"({Path(sys.executable).parent / 'alma'}) or alma-bridge not installed"
            )
        proc = subprocess.run(
            [str(alma_bin), "version"],
            capture_output=True,
            text=True,
            check=False,
        )
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


class TestAlmaCliProviderDecision:
    """Regression: coverage ranking must not imply eligibility or recommendation."""

    @staticmethod
    def _sqlite_like_analysis() -> CompatibilityAnalysisResult:
        """Both providers incompatible; wine has highest coverage (SQLite-like)."""
        provenance = ProvenanceEvidence(
            source="test",
            artifact_id="sqlite_like_fixture",
        )
        native = ProviderCoverageBreakdown(
            provider_id="native_alma",
            supported=10,
            partial=0,
            unsupported=50,
            unknown=5,
            total=65,
            coverage_percent=15.4,
            blockers=["unsupported_api:sqlite3_open"],
        )
        wine = ProviderCoverageBreakdown(
            provider_id="wine",
            supported=120,
            partial=10,
            unsupported=142,
            unknown=0,
            total=272,
            coverage_percent=47.8,
            blockers=["unsupported_api:sqlite3_open"],
        )
        prediction = CompatibilityPrediction(
            native_compatible=False,
            wine_compatible=False,
            needs_unsupported_apis=True,
            confidence=ConfidenceAssessment(
                level=ConfidenceLevelName.LOW,
                score=0.2,
                factors=["unsupported_apis"],
                provenance=provenance,
            ),
            potential_blockers=["unsupported_api:sqlite3_open"] * 142,
            recommended_provider_id=None,
            evidence_summary="native=no; wine=no; confidence=low(0.2); blockers=142",
        )
        return CompatibilityAnalysisResult(
            schema_version=ACI_SCHEMA_VERSION,
            analysis_id="aci-sqlite-like",
            file_path="/tmp/sqlite3.exe",
            binary_digest="digest-sqlite-like",
            metadata=PeAnalysisMetadata(
                architecture="AMD64",
                subsystem="WINDOWS_CUI",
                entry_point_rva=4096,
                image_size=65536,
                is_pe32_plus=True,
                has_tls=False,
                has_relocations=True,
                has_clr=False,
                has_manifest=False,
                has_debug=False,
                has_load_config=False,
                has_exception_directory=False,
                export_count=0,
            ),
            required_capabilities=[
                CapabilityRequirement(
                    capability_id="filesystem.basic_io",
                    description="File I/O",
                )
            ],
            coverage=CoverageReport(
                total_capabilities=1,
                total_apis=272,
                known_apis=272,
                unknown_apis=0,
                providers={"native_alma": native, "wine": wine},
                unsupported_api_names=["sqlite3_open"],
            ),
            prediction=prediction,
            graph=CompatibilityGraph(),
            provenance=provenance,
        )

    def test_provider_decision_sqlite_like(self):
        analysis = self._sqlite_like_analysis()
        decision = resolve_provider_decision(analysis)
        assert decision.highest_coverage_provider == "wine"
        assert decision.highest_coverage_eligible is False
        assert decision.recommended_provider is None
        assert decision.selected_execution_provider is None
        assert decision.eligible_provider is None
        assert decision.prediction_status == "no_eligible_provider"

    @patch("alma_bridge.cli.handlers.resolve_executable_path", return_value="/tmp/sqlite3.exe")
    @patch("alma_bridge.cli.handlers.analyze_executable")
    def test_analyze_json_sqlite_like(self, mock_analyze, _mock_resolve):
        mock_analyze.return_value = self._sqlite_like_analysis()
        result = runner.invoke(alma_app.app, ["--json", "analyze", "/tmp/sqlite3.exe"])
        assert result.exit_code == 0
        payload = _parse_json_stdout(result)
        data = payload["data"]
        decision = data["provider_decision"]
        assert decision["highest_coverage_provider"] == "wine"
        assert decision["recommended_provider"] is None
        assert data["prediction"]["recommended_provider_id"] is None
        assert data["prediction"]["prediction_status"] == "no_eligible_provider"

    @patch("alma_bridge.cli.handlers.resolve_executable_path", return_value="/tmp/sqlite3.exe")
    @patch("alma_bridge.cli.handlers.analyze_executable")
    def test_inspect_json_sqlite_like(self, mock_analyze, _mock_resolve):
        mock_analyze.return_value = self._sqlite_like_analysis()
        result = runner.invoke(alma_app.app, ["--json", "inspect", "/tmp/sqlite3.exe"])
        assert result.exit_code == 0
        data = _parse_json_stdout(result)["data"]
        assert data["recommended_provider_id"] is None
        assert data["provider_decision"]["highest_coverage_provider"] == "wine"
        assert data["provider_decision"]["highest_coverage_eligible"] is False
        assert data["native_compatible"] is False
        assert data["wine_compatible"] is False

    @patch("alma_bridge.cli.handlers.resolve_executable_path", return_value="/tmp/sqlite3.exe")
    @patch("alma_bridge.cli.handlers.analyze_executable")
    def test_predict_json_sqlite_like(self, mock_analyze, _mock_resolve):
        mock_analyze.return_value = self._sqlite_like_analysis()
        result = runner.invoke(alma_app.app, ["--json", "predict", "/tmp/sqlite3.exe"])
        assert result.exit_code == 0
        data = _parse_json_stdout(result)["data"]
        assert data["recommended_provider_id"] is None
        assert data["selected_provider_id"] is None
        assert data["prediction"]["prediction_status"] == "no_eligible_provider"
        assert "No execution provider is recommended" in data["disclaimer"]
        assert data["provider_decision"]["highest_coverage_provider"] == "wine"

    @patch("alma_bridge.cli.handlers.resolve_executable_path", return_value="/tmp/sqlite3.exe")
    @patch("alma_bridge.cli.handlers.analyze_executable")
    def test_inspect_rich_shows_highest_coverage_not_eligible(self, mock_analyze, _mock_resolve):
        mock_analyze.return_value = self._sqlite_like_analysis()
        result = runner.invoke(alma_app.app, ["inspect", "/tmp/sqlite3.exe"])
        assert result.exit_code == 0
        assert "highest coverage, not eligible" in result.stdout.lower()
        assert "wine" in result.stdout.lower()

    @patch("alma_bridge.cli.handlers.resolve_executable_path", return_value="/tmp/sqlite3.exe")
    @patch("alma_bridge.cli.handlers.analyze_executable")
    def test_analyze_rich_agrees_with_json(self, mock_analyze, _mock_resolve):
        mock_analyze.return_value = self._sqlite_like_analysis()
        rich = runner.invoke(alma_app.app, ["analyze", "/tmp/sqlite3.exe"])
        json_result = runner.invoke(alma_app.app, ["--json", "analyze", "/tmp/sqlite3.exe"])
        data = _parse_json_stdout(json_result)["data"]
        assert rich.exit_code == 0
        assert data["provider_decision"]["recommended_provider"] is None
        assert "—" in rich.stdout or "none" in rich.stdout.lower()
        assert "highest coverage, not eligible" in rich.stdout.lower()

    @patch("alma_bridge.cli.handlers.resolve_executable_path", return_value="/tmp/sqlite3.exe")
    @patch("alma_bridge.cli.handlers.analyze_executable")
    def test_run_fail_closed_no_eligible_provider(self, mock_analyze, _mock_resolve):
        mock_analyze.return_value = self._sqlite_like_analysis()
        result = runner.invoke(alma_app.app, ["run", "/tmp/sqlite3.exe"])
        assert result.exit_code == 1
        assert "No eligible execution provider" in result.stdout

    @patch("alma_bridge.cli.handlers.resolve_executable_path", return_value="/tmp/sqlite3.exe")
    @patch("alma_bridge.cli.handlers._orchestrator")
    def test_run_allows_explicit_strategy_override(self, mock_orchestrator_factory, _mock_resolve):
        orchestrator = MagicMock()
        mock_orchestrator_factory.return_value = orchestrator
        orchestrator.run.return_value = BridgeSessionResult(
            session_id="sess-override",
            file_path="/tmp/sqlite3.exe",
            file_hash="digest-sqlite-like",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            success=False,
            summary="forced",
            attempts=[],
        )
        result = runner.invoke(
            alma_app.app,
            ["run", "/tmp/sqlite3.exe", "--strategy", "wine_host"],
        )
        assert result.exit_code == 2
        orchestrator.run.assert_called_once()


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
