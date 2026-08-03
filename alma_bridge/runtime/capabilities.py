"""Runtime capability declarations and states."""

from __future__ import annotations

from enum import Enum
from typing import Dict

from pydantic import BaseModel, Field


class CapabilityState(str, Enum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"
    DELEGATED = "delegated"


# Canonical capability keys shared across providers.
PE_CONSOLE = "pe_console"
PE_GUI = "pe_gui"
PE_INSTALLER = "pe_installer"
PE_ELECTRON = "pe_electron"
ELF_NATIVE = "elf_native"
ELF32_MULTIARCH = "elf32_multiarch"
ELF_FOREIGN_QEMU = "elf_foreign_qemu"
CONTAINER_ISOLATION = "container_isolation"
REGISTRY_MUTATION = "registry_mutation"
DLL_OVERRIDE = "dll_override"


ALL_CAPABILITY_KEYS = (
    PE_CONSOLE,
    PE_GUI,
    PE_INSTALLER,
    PE_ELECTRON,
    ELF_NATIVE,
    ELF32_MULTIARCH,
    ELF_FOREIGN_QEMU,
    CONTAINER_ISOLATION,
    REGISTRY_MUTATION,
    DLL_OVERRIDE,
)


class RuntimeCapabilities(BaseModel):
    """Declared capability states for a compatibility runtime provider."""

    states: Dict[str, CapabilityState] = Field(default_factory=dict)

    def state_of(self, capability: str) -> CapabilityState:
        return self.states.get(capability, CapabilityState.UNKNOWN)

    def supports(self, capability: str) -> bool:
        return self.state_of(capability) in {
            CapabilityState.SUPPORTED,
            CapabilityState.PARTIAL,
            CapabilityState.DELEGATED,
        }

    @classmethod
    def from_states(cls, **kwargs: CapabilityState) -> RuntimeCapabilities:
        return cls(states=dict(kwargs))

    def to_dict(self) -> Dict[str, str]:
        return {key: self.state_of(key).value for key in ALL_CAPABILITY_KEYS}
