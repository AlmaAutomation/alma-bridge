"""Native Alma runtime fail-closed tests."""

from __future__ import annotations

import pytest

from alma_bridge.runtime.capabilities import CapabilityState, PE_CONSOLE
from alma_bridge.runtime.errors import RuntimeNotSupportedError
from alma_bridge.runtime.providers.native_alma import NativeAlmaRuntime


class TestNativeAlmaRuntime:
    def test_fail_closed_inspect(self):
        runtime = NativeAlmaRuntime()
        inspection = runtime.inspect("/tmp/test.exe")
        assert inspection.ready is False

    def test_fail_closed_prepare(self):
        runtime = NativeAlmaRuntime()
        with pytest.raises(RuntimeNotSupportedError):
            runtime.prepare("/tmp/test.exe")

    def test_minimal_console_pe_capability_only(self):
        runtime = NativeAlmaRuntime()
        caps = runtime.capabilities()
        assert caps.state_of(PE_CONSOLE) == CapabilityState.UNKNOWN
        assert caps.state_of("pe_gui") == CapabilityState.UNKNOWN
