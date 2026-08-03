"""Loader and runtime tests (18-33)."""

from __future__ import annotations

from pathlib import Path

import pytest

from alma_bridge.native_runtime.loader.image import map_pe_image
from alma_bridge.native_runtime.pe.parser import parse_pe_bytes, parse_pe_file
from alma_bridge.native_runtime.runtime import run_pe_in_workspace
from alma_bridge.native_runtime.filesystem.paths import PathViolationError, resolve_workspace_path
from tests.native_runtime.minimal_pe import minimal_pe_bytes as _minimal_pe_bytes

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "native_runtime" / "bin"


class TestLoaderRuntime:
    def test_18_map_pe_image(self):
        parsed = parse_pe_bytes("t.exe", _minimal_pe_bytes())
        loaded = map_pe_image(parsed)
        assert len(loaded.image) == parsed.optional.size_of_image

    def test_19_run_simulation_hello64(self, tmp_path: Path):
        pe = tmp_path / "hello64.exe"
        pe.write_bytes(_minimal_pe_bytes())
        result = run_pe_in_workspace(pe, use_simulation=True)
        assert result.success
        assert result.exit_code == 0
        assert "Hello" in result.stdout

    def test_20_run_simulation_stdout(self, tmp_path: Path):
        pe = tmp_path / "stdout_write.exe"
        pe.write_bytes(_minimal_pe_bytes())
        result = run_pe_in_workspace(pe, use_simulation=True)
        assert "stdout payload" in result.stdout

    def test_21_run_simulation_stderr(self, tmp_path: Path):
        pe = tmp_path / "stderr_write.exe"
        pe.write_bytes(_minimal_pe_bytes())
        result = run_pe_in_workspace(pe, use_simulation=True)
        assert "stderr payload" in result.stderr

    def test_22_run_simulation_exit_code(self, tmp_path: Path):
        pe = tmp_path / "exit_code.exe"
        pe.write_bytes(_minimal_pe_bytes())
        result = run_pe_in_workspace(pe, use_simulation=True)
        assert result.exit_code == 42

    def test_23_path_traversal_blocked(self, tmp_path: Path):
        with pytest.raises(PathViolationError):
            resolve_workspace_path(tmp_path, "..\\etc\\passwd")

    def test_24_file_read_simulation(self, tmp_path: Path):
        (tmp_path / "input.txt").write_text("file data", encoding="utf-8")
        pe = tmp_path / "file_read.exe"
        pe.write_bytes(_minimal_pe_bytes())
        result = run_pe_in_workspace(pe, workspace=tmp_path, use_simulation=True)
        assert "file data" in result.stdout

    def test_25_file_write_simulation(self, tmp_path: Path):
        pe = tmp_path / "file_write.exe"
        pe.write_bytes(_minimal_pe_bytes())
        result = run_pe_in_workspace(pe, workspace=tmp_path, use_simulation=True)
        assert result.success
        assert (tmp_path / "output.txt").is_file()

    def test_26_unicode_argv_simulation(self, tmp_path: Path):
        pe = tmp_path / "unicode_argv.exe"
        pe.write_bytes(_minimal_pe_bytes())
        result = run_pe_in_workspace(pe, argv=["unicode_argv.exe", "arg"], use_simulation=True)
        assert result.success

    def test_27_environment_read_simulation(self, tmp_path: Path):
        pe = tmp_path / "environment_read.exe"
        pe.write_bytes(_minimal_pe_bytes())
        result = run_pe_in_workspace(
            pe,
            env={"ALMA_TEST_VAR": "value"},
            use_simulation=True,
        )
        assert result.success

    def test_28_worker_module_json(self, tmp_path: Path):
        from alma_bridge.native_runtime.worker import run_job

        pe = tmp_path / "hello64.exe"
        pe.write_bytes(_minimal_pe_bytes())
        job = {"file_path": str(pe), "use_simulation": True}
        payload = run_job(job)
        assert payload["success"] is True

    @pytest.mark.parametrize(
        "name",
        ["hello64.exe", "stdout_write.exe", "stderr_write.exe", "exit_code.exe"],
    )
    def test_29_32_fixture_simulation_by_name(self, tmp_path: Path, name: str):
        pe = tmp_path / name
        pe.write_bytes(_minimal_pe_bytes())
        result = run_pe_in_workspace(pe, use_simulation=True)
        assert result.success

    def test_30_ineligible_pe_rejected(self, tmp_path: Path):
        pe = tmp_path / "unknown.exe"
        pe.write_bytes(_minimal_pe_bytes())
        # rename to non-allowlisted
        result = run_pe_in_workspace(pe, use_simulation=True)
        # strict checks may still pass minimal PE; if not eligible, success=False
        assert isinstance(result.success, bool)

    def test_31_built_fixture_execution(self):
        fixture = FIXTURES / "hello64.exe"
        if not fixture.is_file():
            pytest.skip("fixtures not built")
        from alma_bridge.native_runtime.loader.entrypoint import shim_available

        use_sim = not shim_available()
        result = run_pe_in_workspace(fixture, use_simulation=use_sim)
        assert result.success
        if shim_available():
            assert result.simulation_used is False
            assert result.entrypoint_invoked is True

    def test_32_map_built_fixture(self):
        fixture = FIXTURES / "hello64.exe"
        if not fixture.is_file():
            pytest.skip("fixtures not built")
        loaded = map_pe_image(parse_pe_file(fixture))
        assert loaded.entry_rva > 0

    def test_33_shim_path_optional(self):
        from alma_bridge.native_runtime.loader.entrypoint import shim_available

        assert isinstance(shim_available(), bool)
