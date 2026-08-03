"""Conformance tests (39-45)."""

from __future__ import annotations

from pathlib import Path

import pytest

from alma_bridge.config import settings
from alma_bridge.runtime.conformance.models import ConformanceClassification
from alma_bridge.runtime.conformance.runner import ConformanceRunner
from alma_bridge.runtime.conformance.scenarios import DEFAULT_SCENARIOS
from alma_bridge.runtime.errors import RuntimeNotSupportedError
from alma_bridge.runtime.providers.native_alma import NativeAlmaRuntime
from alma_bridge.runtime.registry import build_default_registry

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "native_runtime" / "bin"


class TestConformance:
    def test_39_fail_closed_when_disabled(self):
        runtime = NativeAlmaRuntime()
        with pytest.raises(RuntimeNotSupportedError):
            runtime.prepare("/tmp/test.exe")

    def test_40_inspect_when_disabled(self):
        runtime = NativeAlmaRuntime()
        inspection = runtime.inspect("/tmp/hello64.exe")
        assert inspection.ready is False

    def test_41_scenario_native_fail_closed_structural(self):
        runner = ConformanceRunner(build_default_registry())
        scenario = next(s for s in DEFAULT_SCENARIOS if s.scenario_id == "native_alma_fail_closed")
        result = runner.run_scenario(scenario)
        assert result.classification == ConformanceClassification.CANDIDATE_FAILED

    def test_42_capabilities_unknown_when_disabled(self):
        from alma_bridge.runtime.capabilities import CapabilityState, PE_CONSOLE

        caps = NativeAlmaRuntime().capabilities()
        assert caps.state_of(PE_CONSOLE) == CapabilityState.UNKNOWN

    def test_43_native_vs_wine_scenario_exists(self):
        ids = [s.scenario_id for s in DEFAULT_SCENARIOS]
        assert "native_vs_wine_hello64" in ids

    def test_44_native_launch_with_flags(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "native_runtime_enabled", True)
        monkeypatch.setattr(settings, "allow_experimental_runtimes", True)
        built = FIXTURES / "hello64.exe"
        if built.is_file():
            pe = built
        else:
            from tests.native_runtime.minimal_pe import minimal_pe_bytes

            pe = tmp_path / "hello64.exe"
            pe.write_bytes(minimal_pe_bytes())
        runtime = NativeAlmaRuntime()
        handle = runtime.launch(str(pe))
        obs = runtime.observe(handle)
        runtime.teardown(handle)
        assert obs.exit_code == 0
        assert "Hello" in obs.stdout
        if built.is_file() and obs.metadata.get("simulation_used") is not None:
            assert obs.metadata.get("simulation_used") is False

    def test_45_built_fixture_conformance(self, monkeypatch):
        fixture = FIXTURES / "hello64.exe"
        if not fixture.is_file():
            pytest.skip("fixtures not built")
        monkeypatch.setattr(settings, "native_runtime_enabled", True)
        monkeypatch.setattr(settings, "allow_experimental_runtimes", True)
        runner = ConformanceRunner(build_default_registry())
        scenario = next(s for s in DEFAULT_SCENARIOS if s.scenario_id == "native_vs_wine_hello64")
        result = runner.run_scenario(scenario, file_path=str(fixture))
        assert result.candidate_evidence.get("stdout")
