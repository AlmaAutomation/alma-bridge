"""Container sandbox compatibility runtime provider."""

from __future__ import annotations

from typing import Dict, List, Optional

from alma_bridge.compatibility.strategies import classify_binary
from alma_bridge.execution.container_command import build_container_command
from alma_bridge.hardware.profiler import profile_hardware
from alma_bridge.runtime.capabilities import (
    CapabilityState,
    CONTAINER_ISOLATION,
    ELF32_MULTIARCH,
    ELF_FOREIGN_QEMU,
    ELF_NATIVE,
    PE_CONSOLE,
    PE_GUI,
    PE_INSTALLER,
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


class ContainerRuntime:
    """Thin adapter over existing container execution patterns (Phase 0B)."""

    @property
    def provider_id(self) -> str:
        return "container"

    @property
    def provider_version(self) -> str:
        return _PROVIDER_VERSION

    def capabilities(self) -> RuntimeCapabilities:
        hardware = profile_hardware()
        host_caps = hardware.get("capabilities", {})
        docker = bool(host_caps.get("docker"))
        podman = bool(host_caps.get("podman"))
        isolation = (
            CapabilityState.SUPPORTED
            if docker or podman
            else CapabilityState.UNSUPPORTED
        )
        partial = CapabilityState.PARTIAL if isolation == CapabilityState.SUPPORTED else CapabilityState.UNSUPPORTED
        return RuntimeCapabilities.from_states(
            **{
                CONTAINER_ISOLATION: isolation,
                PE_CONSOLE: partial,
                PE_GUI: partial,
                PE_INSTALLER: partial,
                ELF_NATIVE: partial,
                ELF32_MULTIARCH: partial,
                ELF_FOREIGN_QEMU: partial,
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
        host_caps = hardware.get("capabilities", {})
        ready = bool(host_caps.get("docker") or host_caps.get("podman"))
        notes: List[str] = []
        if not ready:
            notes.append("no container engine available")
        return RuntimeInspection(
            provider_id=self.provider_id,
            file_path=file_path,
            binary_format=binary_format,
            ready=ready,
            notes=notes,
            metadata={
                "docker": bool(host_caps.get("docker")),
                "podman": bool(host_caps.get("podman")),
            },
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
            raise RuntimeNotSupportedError("Container runtime not ready on this host")
        hardware = profile_hardware()
        host_arch = hardware.get("architecture", "x86_64")
        resolved = command or build_container_command(
            file_path,
            host_arch=host_arch,
            binary_format=inspection.binary_format,
        )
        return PrepareResult(
            provider_id=self.provider_id,
            command=resolved,
            env=dict(env or {}),
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
            notes=["Phase 0B: observation delegated to execution/sandbox via orchestrator"],
        )

    def terminate(self, handle: LaunchHandle) -> TerminationResult:
        return TerminationResult(
            provider_id=self.provider_id,
            terminated=False,
            notes=["Phase 0B: termination delegated to execution/sandbox via orchestrator"],
        )

    def teardown(self, handle: LaunchHandle) -> None:
        return None
