"""Capability registry with provider implementation status."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from alma_bridge.compatibility_intelligence.models import (
    ApiComplexity,
    ImplementationStatus,
)


@dataclass(frozen=True)
class CapabilityDefinition:
    capability_id: str
    description: str
    complexity: ApiComplexity
    native: ImplementationStatus
    wine: ImplementationStatus
    proton: ImplementationStatus = ImplementationStatus.DELEGATED
    stability: str = "stable"
    documentation_ref: str = ""


# Fine-grained capability registry seeded from NativeAlmaRuntime M2 + Wine coverage.
CAPABILITY_REGISTRY: Dict[str, CapabilityDefinition] = {
    "filesystem.basic_io": CapabilityDefinition(
        capability_id="filesystem.basic_io",
        description="Create, read, write, and close files via Win32 file APIs",
        complexity=ApiComplexity.MEDIUM,
        native=ImplementationStatus.SUPPORTED,
        wine=ImplementationStatus.SUPPORTED,
        documentation_ref="https://learn.microsoft.com/en-us/windows/win32/fileio/file-management",
    ),
    "console.stdout": CapabilityDefinition(
        capability_id="console.stdout",
        description="Write to standard output handle",
        complexity=ApiComplexity.LOW,
        native=ImplementationStatus.SUPPORTED,
        wine=ImplementationStatus.SUPPORTED,
    ),
    "console.stderr": CapabilityDefinition(
        capability_id="console.stderr",
        description="Write to standard error handle",
        complexity=ApiComplexity.LOW,
        native=ImplementationStatus.SUPPORTED,
        wine=ImplementationStatus.SUPPORTED,
    ),
    "process.exit": CapabilityDefinition(
        capability_id="process.exit",
        description="Terminate process with exit code",
        complexity=ApiComplexity.LOW,
        native=ImplementationStatus.SUPPORTED,
        wine=ImplementationStatus.SUPPORTED,
    ),
    "process.arguments": CapabilityDefinition(
        capability_id="process.arguments",
        description="Read process command line",
        complexity=ApiComplexity.LOW,
        native=ImplementationStatus.SUPPORTED,
        wine=ImplementationStatus.SUPPORTED,
    ),
    "process.environment": CapabilityDefinition(
        capability_id="process.environment",
        description="Read environment variables",
        complexity=ApiComplexity.LOW,
        native=ImplementationStatus.SUPPORTED,
        wine=ImplementationStatus.SUPPORTED,
    ),
    "process.identity": CapabilityDefinition(
        capability_id="process.identity",
        description="Query process and module identity",
        complexity=ApiComplexity.LOW,
        native=ImplementationStatus.SUPPORTED,
        wine=ImplementationStatus.SUPPORTED,
    ),
    "process.timing": CapabilityDefinition(
        capability_id="process.timing",
        description="Sleep and timing APIs",
        complexity=ApiComplexity.LOW,
        native=ImplementationStatus.SUPPORTED,
        wine=ImplementationStatus.SUPPORTED,
    ),
    "error.handling": CapabilityDefinition(
        capability_id="error.handling",
        description="Get/set last Win32 error code",
        complexity=ApiComplexity.LOW,
        native=ImplementationStatus.SUPPORTED,
        wine=ImplementationStatus.SUPPORTED,
    ),
    "gui.windowing": CapabilityDefinition(
        capability_id="gui.windowing",
        description="Create and manage GUI windows (user32/gdi32)",
        complexity=ApiComplexity.HIGH,
        native=ImplementationStatus.UNSUPPORTED,
        wine=ImplementationStatus.SUPPORTED,
    ),
    "com.initialization": CapabilityDefinition(
        capability_id="com.initialization",
        description="COM/OLE initialization and apartment threading",
        complexity=ApiComplexity.HIGH,
        native=ImplementationStatus.UNSUPPORTED,
        wine=ImplementationStatus.PARTIAL,
    ),
    "registry.read": CapabilityDefinition(
        capability_id="registry.read",
        description="Read Windows registry keys and values",
        complexity=ApiComplexity.MEDIUM,
        native=ImplementationStatus.UNSUPPORTED,
        wine=ImplementationStatus.PARTIAL,
    ),
    "registry.write": CapabilityDefinition(
        capability_id="registry.write",
        description="Write Windows registry keys and values",
        complexity=ApiComplexity.MEDIUM,
        native=ImplementationStatus.UNSUPPORTED,
        wine=ImplementationStatus.PARTIAL,
    ),
    "process.creation": CapabilityDefinition(
        capability_id="process.creation",
        description="Create child processes",
        complexity=ApiComplexity.MEDIUM,
        native=ImplementationStatus.UNSUPPORTED,
        wine=ImplementationStatus.SUPPORTED,
    ),
    "threading.basic": CapabilityDefinition(
        capability_id="threading.basic",
        description="Create and synchronize threads",
        complexity=ApiComplexity.MEDIUM,
        native=ImplementationStatus.UNSUPPORTED,
        wine=ImplementationStatus.SUPPORTED,
    ),
    "dotnet.clr": CapabilityDefinition(
        capability_id="dotnet.clr",
        description=".NET CLR metadata and managed runtime",
        complexity=ApiComplexity.HIGH,
        native=ImplementationStatus.UNSUPPORTED,
        wine=ImplementationStatus.PARTIAL,
    ),
    "api.unknown": CapabilityDefinition(
        capability_id="api.unknown",
        description="Unclassified Windows API — coverage unknown",
        complexity=ApiComplexity.MEDIUM,
        native=ImplementationStatus.UNKNOWN,
        wine=ImplementationStatus.UNKNOWN,
        stability="unknown",
    ),
}

PROVIDER_IDS = ("native_alma", "wine", "proton", "container")


def get_capability(capability_id: str) -> Optional[CapabilityDefinition]:
    return CAPABILITY_REGISTRY.get(capability_id)


def list_capabilities() -> List[CapabilityDefinition]:
    return sorted(CAPABILITY_REGISTRY.values(), key=lambda c: c.capability_id)


def provider_status(capability_id: str, provider_id: str) -> ImplementationStatus:
    cap = CAPABILITY_REGISTRY.get(capability_id)
    if cap is None:
        return ImplementationStatus.UNKNOWN
    if provider_id == "native_alma":
        return cap.native
    if provider_id == "wine":
        return cap.wine
    if provider_id == "proton":
        return cap.proton
    if provider_id == "container":
        return ImplementationStatus.DELEGATED
    return ImplementationStatus.UNKNOWN
