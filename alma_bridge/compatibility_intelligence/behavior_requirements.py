"""Behavioral capability profiles — API availability vs API behavior."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from alma_bridge.compatibility_intelligence.models import (
    ApiClassificationResult,
    ImportedFunction,
    PeAnalysisMetadata,
    ProvenanceEvidence,
)


BEHAVIOR_REGISTRY_VERSION = "aci_behavior_registry_v1"


@dataclass(frozen=True)
class CapabilityBehaviorProfile:
    capability_id: str
    provider_id: str
    implementation_version: str
    supported_behaviors: List[str] = field(default_factory=list)
    unsupported_behaviors: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    verified_scenarios: List[str] = field(default_factory=list)
    evidence_references: List[str] = field(default_factory=list)


# Native Alma M2 behavioral profiles — symbol support ≠ behavior support.
BEHAVIOR_PROFILES: Dict[tuple[str, str], CapabilityBehaviorProfile] = {
    ("filesystem.basic_io", "native_alma"): CapabilityBehaviorProfile(
        capability_id="filesystem.basic_io",
        provider_id="native_alma",
        implementation_version="0.2.1-m2",
        supported_behaviors=["create_always_write", "sequential_read", "close_handle", "append_existing_file"],
        unsupported_behaviors=["overlapped_io", "open_existing_readwrite"],
        limitations=[
            "OPEN_EXISTING + FILE_APPEND_DATA append within workspace (0.2.1-m2)",
            "Overlapped I/O unsupported",
        ],
        verified_scenarios=["file_write_fixture", "file_read_fixture", "file_append_fixture"],
        evidence_references=["native-shim:kernel32_shim.c", "docs/native-runtime/append_existing_file_design.md"],
    ),
    ("filesystem.basic_io", "wine"): CapabilityBehaviorProfile(
        capability_id="filesystem.basic_io",
        provider_id="wine",
        implementation_version="stable",
        supported_behaviors=[
            "create_always_write",
            "sequential_read",
            "append_existing_file",
            "open_existing_readwrite",
            "close_handle",
        ],
        unsupported_behaviors=["overlapped_io"],
        limitations=[],
        verified_scenarios=["file_write_fixture", "file_read_fixture", "file_append_fixture"],
        evidence_references=["wine:kernel32"],
    ),
    ("console.stdout", "native_alma"): CapabilityBehaviorProfile(
        capability_id="console.stdout",
        provider_id="native_alma",
        implementation_version="0.2.0-m2",
        supported_behaviors=["write_stdout", "write_stderr"],
        unsupported_behaviors=[],
        limitations=[],
        verified_scenarios=["hello64_fixture", "stdout_write_fixture", "stderr_write_fixture"],
        evidence_references=["native-shim:kernel32_shim.c"],
    ),
    ("process.environment", "native_alma"): CapabilityBehaviorProfile(
        capability_id="process.environment",
        provider_id="native_alma",
        implementation_version="0.2.0-m2",
        supported_behaviors=["read_environment_variable"],
        unsupported_behaviors=["set_environment_variable"],
        limitations=["Environment block from worker only"],
        verified_scenarios=["environment_read_fixture"],
        evidence_references=["native-shim:kernel32_shim.c"],
    ),
    ("process.exit", "native_alma"): CapabilityBehaviorProfile(
        capability_id="process.exit",
        provider_id="native_alma",
        implementation_version="0.2.0-m2",
        supported_behaviors=["process_exit_with_code"],
        unsupported_behaviors=[],
        limitations=[],
        verified_scenarios=["exit_code_fixture", "hello64_fixture"],
        evidence_references=["native-shim:kernel32_shim.c"],
    ),
}


def get_behavior_profile(capability_id: str, provider_id: str) -> Optional[CapabilityBehaviorProfile]:
    return BEHAVIOR_PROFILES.get((capability_id, provider_id))


def list_behavior_profiles(provider_id: Optional[str] = None) -> List[CapabilityBehaviorProfile]:
    profiles = list(BEHAVIOR_PROFILES.values())
    if provider_id:
        profiles = [p for p in profiles if p.provider_id == provider_id]
    return sorted(profiles, key=lambda p: (p.provider_id, p.capability_id))


# Win32 constants for behavior inference from fixture source patterns.
CREATE_ALWAYS = 2
OPEN_EXISTING = 3
FILE_APPEND_DATA = 0x0004
GENERIC_WRITE = 0x40000000


def infer_required_behaviors(
    imports: List[ImportedFunction],
    classifications: List[ApiClassificationResult],
    metadata: PeAnalysisMetadata,
) -> Set[str]:
    """Infer required API behaviors from import set and PE metadata."""
    behaviors: Set[str] = set()
    import_names = {f"{i.dll}!{i.name}".lower() for i in imports}

    if any("writefile" in n for n in import_names):
        behaviors.add("sequential_write")
    if any("createfilew" in n for n in import_names):
        behaviors.add("create_always_write")
        behaviors.add("open_existing_readwrite")
    if any("readfile" in n for n in import_names):
        behaviors.add("sequential_read")
    if any("getenvironmentvariablew" in n for n in import_names):
        behaviors.add("read_environment_variable")
    if any("exitprocess" in n for n in import_names):
        behaviors.add("process_exit_with_code")
    if any("getstdhandle" in n for n in import_names):
        behaviors.add("write_stdout")
    if any("getcommandlinew" in n for n in import_names):
        behaviors.add("read_command_line")
    if metadata.delay_import_dlls:
        behaviors.add("delay_import_resolution")
    if metadata.has_tls:
        behaviors.add("tls_callback_execution")

    cap_ids = {c.capability_id for c in classifications}
    for cap_id in cap_ids:
        profile = get_behavior_profile(cap_id, "native_alma")
        if profile:
            for b in profile.supported_behaviors + profile.unsupported_behaviors:
                pass  # profiles inform coverage_validation, not auto-inference

    return behaviors


def infer_fixture_behaviors(fixture_name: str) -> Set[str]:
    """Explicit behavior requirements for known test fixtures."""
    mapping = {
        "hello64.exe": {"write_stdout", "process_exit_with_code"},
        "file_write.exe": {"create_always_write", "sequential_write"},
        "file_read.exe": {"sequential_read", "open_existing_readwrite"},
        "file_append_unsupported.exe": {"append_existing_file", "sequential_write"},
        "append_existing_success.exe": {"append_existing_file"},
        "append_repeated.exe": {"append_existing_file"},
        "append_unicode.exe": {"append_existing_file"},
        "append_zero_length.exe": {"append_existing_file"},
        "append_invalid_handle.exe": {"append_existing_file"},
        "append_missing_file.exe": {"append_existing_file"},
        "append_path_traversal.exe": {"append_existing_file"},
        "append_overlapped_unsupported.exe": {"overlapped_io", "append_existing_file"},
        "environment_read.exe": {"read_environment_variable", "process_exit_with_code"},
        "exit_code.exe": {"process_exit_with_code"},
        "stdout_write.exe": {"write_stdout", "process_exit_with_code"},
        "stderr_write.exe": {"write_stderr", "process_exit_with_code"},
        "unicode_argv.exe": {"read_command_line", "process_exit_with_code"},
    }
    return set(mapping.get(fixture_name.lower(), set()))


def behaviors_for_capability(capability_id: str, provider_id: str) -> tuple[List[str], List[str]]:
    profile = get_behavior_profile(capability_id, provider_id)
    if profile is None:
        return [], []
    return list(profile.supported_behaviors), list(profile.unsupported_behaviors)
