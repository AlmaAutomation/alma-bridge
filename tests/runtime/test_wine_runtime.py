"""Wine runtime adapter tests."""

from __future__ import annotations

from alma_bridge.runtime.capabilities import CapabilityState, PE_CONSOLE, PE_GUI
from alma_bridge.runtime.providers.wine import WineRuntime


class TestWineRuntime:
    def test_capability_declarations_present(self):
        runtime = WineRuntime()
        caps = runtime.capabilities()
        assert caps.state_of(PE_CONSOLE) in {
            CapabilityState.SUPPORTED,
            CapabilityState.UNSUPPORTED,
        }
        assert caps.state_of(PE_GUI) in {
            CapabilityState.SUPPORTED,
            CapabilityState.UNSUPPORTED,
        }

    def test_provider_id_and_version(self):
        runtime = WineRuntime()
        assert runtime.provider_id == "wine"
        assert runtime.provider_version.startswith("0.")

    def test_prepare_builds_wine_command(self, tmp_path):
        exe = tmp_path / "game.exe"
        exe.write_bytes(b"fake pe")
        runtime = WineRuntime()
        inspection = runtime.inspect(str(exe))
        if not inspection.ready:
            return
        prepared = runtime.prepare(str(exe))
        assert prepared.command[0]
        assert str(exe.resolve()) in prepared.command[-1]
