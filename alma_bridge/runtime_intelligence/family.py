"""Canonical behavior-family mapping for Runtime Intelligence."""

from __future__ import annotations

from typing import Dict, List, Optional

from alma_bridge.compatibility_intelligence.behavior_requirements import BEHAVIOR_PROFILES
from alma_bridge.compatibility_intelligence.capabilities import CAPABILITY_REGISTRY

from alma_bridge.runtime_intelligence.models import (
    BehaviorFamilyId,
    BehaviorFamilyMapping,
    CanonicalFamily,
)

FAMILY_REGISTRY: Dict[str, BehaviorFamilyId] = {
    "filesystem.basic_io": BehaviorFamilyId.FILESYSTEM,
    "console.stdout": BehaviorFamilyId.CONSOLE,
    "console.stderr": BehaviorFamilyId.CONSOLE,
    "process.exit": BehaviorFamilyId.CRT,
    "process.arguments": BehaviorFamilyId.CRT,
    "process.environment": BehaviorFamilyId.CRT,
    "process.identity": BehaviorFamilyId.CRT,
    "process.timing": BehaviorFamilyId.CRT,
    "process.creation": BehaviorFamilyId.CRT,
    "error.handling": BehaviorFamilyId.CRT,
    "dotnet.clr": BehaviorFamilyId.CRT,
    "registry.read": BehaviorFamilyId.REGISTRY,
    "registry.write": BehaviorFamilyId.REGISTRY,
    "threading.basic": BehaviorFamilyId.SYNCHRONIZATION,
    "com.initialization": BehaviorFamilyId.SYNCHRONIZATION,
    "gui.windowing": BehaviorFamilyId.GUI,
}

BEHAVIOR_FAMILY_REGISTRY: Dict[str, BehaviorFamilyId] = {
    "create_always_write": BehaviorFamilyId.FILESYSTEM,
    "sequential_read": BehaviorFamilyId.FILESYSTEM,
    "close_handle": BehaviorFamilyId.FILESYSTEM,
    "append_existing_file": BehaviorFamilyId.FILESYSTEM,
    "overlapped_io": BehaviorFamilyId.FILESYSTEM,
    "open_existing_readwrite": BehaviorFamilyId.FILESYSTEM,
    "sequential_write": BehaviorFamilyId.FILESYSTEM,
    "write_stdout": BehaviorFamilyId.CONSOLE,
    "write_stderr": BehaviorFamilyId.CONSOLE,
    "read_environment_variable": BehaviorFamilyId.CRT,
    "set_environment_variable": BehaviorFamilyId.CRT,
    "process_exit_with_code": BehaviorFamilyId.CRT,
    "read_command_line": BehaviorFamilyId.CRT,
    "delay_import_resolution": BehaviorFamilyId.CRT,
    "tls_callback_execution": BehaviorFamilyId.CRT,
}

CANONICAL_FAMILIES: Dict[BehaviorFamilyId, CanonicalFamily] = {
    BehaviorFamilyId.FILESYSTEM: CanonicalFamily(
        family_id=BehaviorFamilyId.FILESYSTEM,
        name="Filesystem",
        description="File creation, read, write, and handle lifecycle",
    ),
    BehaviorFamilyId.CONSOLE: CanonicalFamily(
        family_id=BehaviorFamilyId.CONSOLE,
        name="Console",
        description="Standard output and standard error streams",
    ),
    BehaviorFamilyId.MEMORY: CanonicalFamily(
        family_id=BehaviorFamilyId.MEMORY,
        name="Memory",
        description="Heap and virtual memory allocation behaviors",
    ),
    BehaviorFamilyId.CRT: CanonicalFamily(
        family_id=BehaviorFamilyId.CRT,
        name="CRT",
        description="Process lifecycle, environment, command line, exit, and error handling",
    ),
    BehaviorFamilyId.REGISTRY: CanonicalFamily(
        family_id=BehaviorFamilyId.REGISTRY,
        name="Registry",
        description="Windows registry read and write operations",
    ),
    BehaviorFamilyId.NETWORKING: CanonicalFamily(
        family_id=BehaviorFamilyId.NETWORKING,
        name="Networking",
        description="Network socket and protocol behaviors",
    ),
    BehaviorFamilyId.SYNCHRONIZATION: CanonicalFamily(
        family_id=BehaviorFamilyId.SYNCHRONIZATION,
        name="Synchronization",
        description="Threading, COM apartment initialization, and synchronization primitives",
    ),
    BehaviorFamilyId.GUI: CanonicalFamily(
        family_id=BehaviorFamilyId.GUI,
        name="GUI",
        description="Window creation and GUI subsystem behaviors",
    ),
}


def family_for_capability(capability_id: str) -> Optional[BehaviorFamilyId]:
    return FAMILY_REGISTRY.get(capability_id)


def family_for_behavior(behavior_id: str) -> Optional[BehaviorFamilyId]:
    return BEHAVIOR_FAMILY_REGISTRY.get(behavior_id)


def list_families() -> List[BehaviorFamilyId]:
    return list(BehaviorFamilyId)


def list_behavior_family_mappings() -> List[BehaviorFamilyMapping]:
    mappings = [
        BehaviorFamilyMapping(behavior_id=behavior_id, family_id=family_id)
        for behavior_id, family_id in sorted(BEHAVIOR_FAMILY_REGISTRY.items())
    ]
    return mappings


def all_registry_capabilities_mapped() -> bool:
    """Return True when every CAPABILITY_REGISTRY entry except api.unknown is mapped."""
    unmapped = [
        capability_id
        for capability_id in CAPABILITY_REGISTRY
        if capability_id != "api.unknown" and capability_id not in FAMILY_REGISTRY
    ]
    return not unmapped


def all_profile_behaviors_mapped() -> bool:
    """Return True when every behavior referenced in BEHAVIOR_PROFILES is mapped."""
    behavior_ids: set[str] = set()
    for profile in BEHAVIOR_PROFILES.values():
        behavior_ids.update(profile.supported_behaviors)
        behavior_ids.update(profile.unsupported_behaviors)
    unmapped = [behavior_id for behavior_id in behavior_ids if behavior_id not in BEHAVIOR_FAMILY_REGISTRY]
    return not unmapped
