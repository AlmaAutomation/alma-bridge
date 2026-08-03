"""Proton compatibility runtime provider."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from alma_bridge.compatibility.strategies import classify_binary, is_pe_path
from alma_bridge.hardware.profiler import profile_hardware
from alma_bridge.hardware.proton import find_best_proton
from alma_bridge.runtime.capabilities import (
    CapabilityState,
    DLL_OVERRIDE,
    PE_CONSOLE,
    PE_ELECTRON,
    PE_GUI,
    PE_INSTALLER,
    REGISTRY_MUTATION,
    RuntimeCapabilities,
)
from alma_bridge.runtime.errors import RuntimeNotSupportedError
from alma_bridge.runtime.models import (
    LaunchHandle,
    PrepareResult,
    RuntimeInspection,
    RuntimeObservation,
    TerminationResult,
)

_PROVIDER_VERSION = "0.1.0"


class ProtonRuntime:
    """Thin adapter over existing Proton execution patterns (Phase 0B)."""

    @property
    def provider_id(self) -> str:
        return "proton"

    @property
    def provider_version(self) -> str:
        return _PROVIDER_VERSION

    def capabilities(self) -> RuntimeCapabilities:
        hardware = profile_hardware()
        host_caps = hardware.get("capabilities", {})
        proton_available = bool(host_caps.get("proton"))
        base = CapabilityState.SUPPORTED if proton_available else CapabilityState.UNSUPPORTED
        return RuntimeCapabilities.from_states(
            **{
                PE_CONSOLE: base,
                PE_GUI: CapabilityState.SUPPORTED if proton_available else CapabilityState.UNSUPPORTED,
                PE_INSTALLER: CapabilityState.PARTIAL if proton_available else CapabilityState.UNSUPPORTED,
                PE_ELECTRON: CapabilityState.PARTIAL if proton_available else CapabilityState.UNSUPPORTED,
                REGISTRY_MUTATION: CapabilityState.DELEGATED if proton_available else CapabilityState.UNSUPPORTED,
                DLL_OVERRIDE: CapabilityState.DELEGATED if proton_available else CapabilityState.UNSUPPORTED,
            }
        )

    def inspect(
        self,
        file_path: str,
        *,
        env: Optional[Dict[str, str]] = None,
    ) -> RuntimeInspection:
        hardware = profile_hardware()
        host_arch = hardware.get("architecture", "x86_64")
        binary_format = classify_binary(file_path, host_arch)
        proton_path = find_best_proton() or hardware.get("paths", {}).get("proton")
        notes: List[str] = []
        ready = bool(hardware.get("capabilities", {}).get("proton"))
        if binary_format != "pe" and not is_pe_path(file_path):
            notes.append("binary is not PE; Proton may not apply")
            ready = False
        return RuntimeInspection(
            provider_id=self.provider_id,
            file_path=file_path,
            binary_format=binary_format,
            ready=ready,
            notes=notes,
            metadata={"proton_path": proton_path},
        )

    def prepare(
        self,
        file_path: str,
        *,
        command: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> PrepareResult:
        inspection = self.inspect(file_path, env=env)
        if not inspection.ready:
            raise RuntimeNotSupportedError("Proton runtime not ready for this target")
        merged_env = dict(env or {})
        resolved = command or self._default_command(file_path)
        return PrepareResult(
            provider_id=self.provider_id,
            command=resolved,
            env=merged_env,
            ready=True,
        )

    def launch(
        self,
        file_path: str,
        *,
        command: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> LaunchHandle:
        prepared = self.prepare(file_path, command=command, env=env)
        return LaunchHandle(
            provider_id=self.provider_id,
            command=prepared.command,
            env=prepared.env,
            launched=False,
        )

    def observe(self, handle: LaunchHandle) -> RuntimeObservation:
        return RuntimeObservation(
            provider_id=self.provider_id,
            running=False,
            notes=["Phase 0B: observation delegated to execution/runner via orchestrator"],
        )

    def terminate(self, handle: LaunchHandle) -> TerminationResult:
        return TerminationResult(
            provider_id=self.provider_id,
            terminated=False,
            notes=["Phase 0B: termination delegated to execution/runner via orchestrator"],
        )

    def teardown(self, handle: LaunchHandle) -> None:
        return None

    def _default_command(self, file_path: str) -> List[str]:
        hardware = profile_hardware()
        proton_path = find_best_proton() or hardware.get("paths", {}).get("proton") or "proton"
        return [proton_path, "run", str(Path(file_path).resolve())]
