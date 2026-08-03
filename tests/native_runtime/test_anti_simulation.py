"""Anti-simulation proof tests (mandatory M2)."""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from alma_bridge.native_runtime.eligibility import manifest_match, pe_binary_digest
from alma_bridge.native_runtime.loader.entrypoint import shim_available
from alma_bridge.native_runtime.loader.image import map_pe_image
from alma_bridge.native_runtime.pe.parser import parse_pe_file
from alma_bridge.native_runtime.runtime import run_pe_in_workspace

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "native_runtime"
BIN = FIXTURES / "bin"
SRC = FIXTURES / "src"
SHIM = Path(__file__).resolve().parents[2] / "alma_bridge" / "native_runtime" / "shim"


@pytest.fixture(scope="module")
def require_shim_and_fixtures():
    if not shim_available():
        pytest.skip("libalma_native_shim.so not built")
    if not (BIN / "hello64.exe").is_file():
        pytest.skip("fixtures not built")


class TestAntiSimulation:
    def test_01_real_hello64_not_hardcoded_simulation(self, require_shim_and_fixtures):
        result = run_pe_in_workspace(BIN / "hello64.exe")
        assert result.success
        assert result.simulation_used is False
        assert result.entrypoint_invoked is True
        assert result.native_execution_mode == "mapped_pe_entrypoint"
        assert "Hello, Alma!" in result.stdout
        assert "Hello, Alma!" not in Path(SHIM / "kernel32_shim.c").read_text()

    def test_02_custom_message_without_runtime_change(self, require_shim_and_fixtures, tmp_path: Path):
        custom_src = tmp_path / "custom_hello.c"
        custom_src.write_text(
            (SRC / "hello64.c").read_text().replace("Hello, Alma!", "Custom PE Message!"),
            encoding="utf-8",
        )
        out = tmp_path / "custom_hello.exe"
        subprocess.run(
            [
                "x86_64-w64-mingw32-gcc",
                "-O2",
                "-o",
                str(out),
                str(custom_src),
                "-lkernel32",
                "-e",
                "entry",
                "-nostartfiles",
                "-Wl,--subsystem,console",
            ],
            check=True,
            capture_output=True,
        )
        result = run_pe_in_workspace(out)
        assert result.success
        assert "Custom PE Message!" in result.stdout
        assert "Hello, Alma!" not in result.stdout

    def test_03_renamed_file_same_behavior_via_digest(self, require_shim_and_fixtures, tmp_path: Path):
        original = BIN / "hello64.exe"
        digest = pe_binary_digest(original)
        renamed = tmp_path / "renamed_output.exe"
        renamed.write_bytes(original.read_bytes())
        assert pe_binary_digest(renamed) == digest
        assert manifest_match(renamed) or renamed.name.lower() in {"hello64.exe"}
        result = run_pe_in_workspace(renamed)
        assert result.success
        assert "Hello, Alma!" in result.stdout
        assert result.simulation_used is False

    def test_04_simulation_only_when_explicit(self, require_shim_and_fixtures, monkeypatch):
        monkeypatch.delenv("ALMA_NATIVE_SIMULATION", raising=False)
        real = run_pe_in_workspace(BIN / "hello64.exe", use_simulation=False)
        assert real.simulation_used is False
        sim = run_pe_in_workspace(BIN / "hello64.exe", use_simulation=True)
        assert sim.simulation_used is True
        assert sim.native_execution_mode == "python_fixture_simulation"

    def test_05_simulation_env_diagnostic_mode(self, require_shim_and_fixtures, monkeypatch):
        monkeypatch.setenv("ALMA_NATIVE_SIMULATION", "1")
        result = run_pe_in_workspace(BIN / "hello64.exe")
        assert result.simulation_used is True
        assert result.entrypoint_invoked is False

    def test_06_evidence_fields_present(self, require_shim_and_fixtures):
        result = run_pe_in_workspace(BIN / "hello64.exe")
        assert result.binary_digest == hashlib.sha256((BIN / "hello64.exe").read_bytes()).hexdigest()
        assert result.simulation_used is False
        assert result.entrypoint_invoked is True
        assert result.native_execution_mode == "mapped_pe_entrypoint"

    def test_07_forced_relocation_delta_python_mapper(self, require_shim_and_fixtures):
        parsed = parse_pe_file(BIN / "hello64.exe")
        preferred = parsed.optional.image_base
        loaded = map_pe_image(parsed, load_base=preferred + 0x10000)
        assert loaded.base_address == preferred + 0x10000

    def test_08_production_path_rejects_missing_shim(self, require_shim_and_fixtures, monkeypatch):
        monkeypatch.delenv("ALMA_NATIVE_SIMULATION", raising=False)
        monkeypatch.setattr(
            "alma_bridge.native_runtime.runtime.shim_available",
            lambda: False,
        )
        result = run_pe_in_workspace(BIN / "hello64.exe")
        assert result.success is False
        assert "shim" in (result.error or "").lower()
