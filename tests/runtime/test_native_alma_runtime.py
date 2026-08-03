"""Native Alma runtime fail-closed and enabled-path tests."""

from __future__ import annotations

import pytest

from alma_bridge.config import settings
from alma_bridge.runtime.capabilities import CapabilityState, PE_CONSOLE
from alma_bridge.runtime.errors import RuntimeNotSupportedError
from alma_bridge.runtime.providers.native_alma import NativeAlmaRuntime
from tests.native_runtime.minimal_pe import minimal_pe_bytes


def _minimal_pe(path: Path) -> None:
    path.write_bytes(minimal_pe_bytes())


class TestNativeAlmaRuntime:
    def test_fail_closed_inspect(self):
        runtime = NativeAlmaRuntime()
        inspection = runtime.inspect("/tmp/hello64.exe")
        assert inspection.ready is False

    def test_fail_closed_prepare(self):
        runtime = NativeAlmaRuntime()
        with pytest.raises(RuntimeNotSupportedError):
            runtime.prepare("/tmp/hello64.exe")

    def test_console_pe_capability_unknown_when_disabled(self):
        runtime = NativeAlmaRuntime()
        caps = runtime.capabilities()
        assert caps.state_of(PE_CONSOLE) == CapabilityState.UNKNOWN

    def test_enabled_inspect_eligible_fixture(self, monkeypatch, tmp_path: Path):
        monkeypatch.setattr(settings, "native_runtime_enabled", True)
        monkeypatch.setattr(settings, "allow_experimental_runtimes", True)
        pe = tmp_path / "hello64.exe"
        _minimal_pe(pe)
        runtime = NativeAlmaRuntime()
        inspection = runtime.inspect(str(pe))
        assert inspection.ready is True
        assert inspection.metadata.get("eligible") is True
