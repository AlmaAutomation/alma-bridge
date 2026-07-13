"""Domain models for the automated compatibility bridge orchestrator."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from alma_bridge.schemas.models import AttemptRecord


BRIDGE_DOMAIN_VERSION = "1.0"


class GapCategory(str, Enum):
    ARCHITECTURE_MISMATCH = "architecture_mismatch"
    ABI_MISMATCH = "abi_mismatch"
    MISSING_DEPENDENCY = "missing_dependency"
    INCOMPATIBLE_DEPENDENCY_VERSION = "incompatible_dependency_version"
    MISSING_RUNTIME = "missing_runtime"
    UNSUPPORTED_OS_INTERFACE = "unsupported_operating_system_interface"
    FILESYSTEM_EXPECTATION_MISMATCH = "filesystem_expectation_mismatch"
    ENVIRONMENT_CONFIGURATION_MISMATCH = "environment_configuration_mismatch"
    GRAPHICS_API_MISMATCH = "graphics_api_mismatch"
    DRIVER_MISMATCH = "driver_mismatch"
    PERMISSION_MISMATCH = "permission_mismatch"
    DEPRECATED_API = "deprecated_api"
    UNAVAILABLE_SERVICE = "unavailable_service"
    UNKNOWN_RUNTIME_FAILURE = "unknown_runtime_failure"
    PROGRAM_NOT_FOUND = "program_not_found"
    GUI_UNAVAILABLE = "gui_unavailable"


class BridgeComponentKind(str, Enum):
    ISOLATED_RUNTIME = "isolated_runtime"
    COMPATIBILITY_LIBRARY = "compatibility_library"
    DEPENDENCY_LAYER = "dependency_layer"
    ENVIRONMENT_ADAPTER = "environment_adapter"
    FILESYSTEM_ADAPTER = "filesystem_adapter"
    API_TRANSLATION_LAYER = "api_translation_layer"
    ARCHITECTURE_TRANSLATION = "architecture_translation"
    CONTAINER = "container"
    VM = "vm"
    WRAPPER = "wrapper"
    LAUNCHER = "launcher"
    CONFIGURATION_OVERLAY = "configuration_overlay"


class ExecutionScope(str, Enum):
    HOST = "host"
    HOST_PREFIX = "host_prefix"
    CONTAINER = "container"
    VM = "vm"


class ProgramIdentity(BaseModel):
    path: str
    filename: str
    sha256: Optional[str] = None
    size_bytes: Optional[int] = None
    fingerprint: str = ""
    exists: bool = False


class LibraryRef(BaseModel):
    name: str
    path: Optional[str] = None
    required: bool = True
    resolved: Optional[bool] = None


class RuntimeRequirement(BaseModel):
    runtime: str
    version_hint: Optional[str] = None
    required: bool = True
    reason: str = ""


class GraphicsRequirement(BaseModel):
    api: str = "unknown"
    software_fallback_ok: bool = True
    gpu_required: bool = False


class ProgramProfile(BaseModel):
    schema_version: str = BRIDGE_DOMAIN_VERSION
    identity: ProgramIdentity
    format: Literal["elf", "elf32", "elf_foreign", "pe", "msi", "script", "appimage", "missing", "unknown"] = "unknown"
    architecture: str = "unknown"
    abi: Optional[str] = None
    program_kind: str = "unknown"
    profile: str = "generic"
    is_installer: bool = False
    is_electron: bool = False
    is_launcher: bool = False
    needs_wine: bool = False
    needs_gui: bool = False
    needs_native: bool = False
    required_libraries: List[LibraryRef] = Field(default_factory=list)
    optional_libraries: List[LibraryRef] = Field(default_factory=list)
    runtime_requirements: List[RuntimeRequirement] = Field(default_factory=list)
    interpreter: Optional[str] = None
    environment_hints: Dict[str, str] = Field(default_factory=dict)
    filesystem_expectations: List[str] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=list)
    graphics_requirements: Optional[GraphicsRequirement] = None
    network_expectations: List[str] = Field(default_factory=list)
    observed_startup_markers: List[str] = Field(default_factory=list)
    known_incompatibilities: List[str] = Field(default_factory=list)
    source: str = "bridge"


class HostCapabilityProfile(BaseModel):
    schema_version: str = BRIDGE_DOMAIN_VERSION
    host_fingerprint: str = ""
    hostname: str = ""
    os: str = ""
    os_version: str = ""
    distribution: Optional[str] = None
    kernel: Optional[str] = None
    architecture: str = "unknown"
    os_bitness: str = "unknown"
    capabilities: Dict[str, bool] = Field(default_factory=dict)
    paths: Dict[str, Optional[str]] = Field(default_factory=dict)
    installed_runtimes: List[str] = Field(default_factory=list)
    gpu: Dict[str, Any] = Field(default_factory=dict)
    legacy_indicators: List[str] = Field(default_factory=list)
    security_policies: Dict[str, Any] = Field(default_factory=dict)
    resources: Dict[str, Any] = Field(default_factory=dict)
    display_available: bool = False


class WineEnvironmentProfile(BaseModel):
    """Wine prefix state — required for PE installers/launchers beyond host Wine."""

    schema_version: str = BRIDGE_DOMAIN_VERSION
    wine_prefix: Optional[str] = None
    prefix_exists: bool = False
    prefix_writable: bool = False
    windows_version: Optional[str] = None
    vcrun_ready: bool = False
    dotnet_ready: bool = False
    runtimes_ready: bool = False
    mingw_compiler_available: bool = False
    electron_wrappers_needed: bool = False
    installed_launcher_path: Optional[str] = None


class CompatibilityGap(BaseModel):
    id: str
    category: GapCategory
    severity: Literal["blocker", "major", "minor", "unknown"] = "major"
    description: str
    evidence: List[str] = Field(default_factory=list)
    required_component_kinds: List[BridgeComponentKind] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)
    suggested_protocol_ids: List[str] = Field(default_factory=list)


class BridgeComponent(BaseModel):
    id: str
    kind: BridgeComponentKind
    operation_id: str
    params: Dict[str, Any] = Field(default_factory=dict)
    scope: ExecutionScope = ExecutionScope.HOST
    reversible: bool = True
    risk: Literal["low", "medium", "high"] = "low"
    requires_approval: bool = False


class VerificationCheckKind(str, Enum):
    PROCESS_STARTS = "process_starts"
    PROCESS_SURVIVES = "process_survives"
    EXIT_CODE_ZERO = "exit_code_zero"
    LOG_EXCLUDES_SIGNATURE = "log_excludes_signature"
    LOG_INCLUDES_MARKER = "log_includes_marker"
    PREFIX_HAS_LAUNCHER = "prefix_has_launcher"
    PREFIX_RUNTIME_READY = "prefix_runtime_ready"
    NO_RUNDLL32_PROCESS = "no_rundll32_process"
    SIDECAR_OUTPUT = "sidecar_output"
    MAIN_LAUNCHER_NOT_DECOY = "main_launcher_not_decoy"


class VerificationCheck(BaseModel):
    kind: VerificationCheckKind
    params: Dict[str, Any] = Field(default_factory=dict)
    weight: float = 1.0
    critical: bool = True


class VerificationContract(BaseModel):
    id: str
    checks: List[VerificationCheck] = Field(default_factory=list)
    min_survival_sec: float = 0.0
    required_pass_count: Optional[int] = None
    application_specific: bool = False


class CompatibilityBridgePlan(BaseModel):
    plan_id: str
    program_fingerprint: str
    host_fingerprint: str
    gaps: List[CompatibilityGap] = Field(default_factory=list)
    components: List[BridgeComponent] = Field(default_factory=list)
    execution_scope: ExecutionScope = ExecutionScope.HOST
    strategy_id: str = ""
    launch_command: List[str] = Field(default_factory=list)
    launch_env: Dict[str, str] = Field(default_factory=dict)
    launch_args: List[str] = Field(default_factory=list)
    verification_contract_id: str = ""
    rollback_plan_id: Optional[str] = None
    reuse_profile_id: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    requires_human_approval: bool = False
    planner_version: str = "heuristic-v1"


class RuntimeObservation(BaseModel):
    session_id: str = ""
    attempt_number: int = 0
    phase: str = "run"
    processes: List[Dict[str, Any]] = Field(default_factory=list)
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""
    sidecar_logs: List[str] = Field(default_factory=list)
    resource_usage: Dict[str, Any] = Field(default_factory=dict)
    anomalies: List[str] = Field(default_factory=list)


class VerificationResult(BaseModel):
    passed: bool = False
    evidence: List[str] = Field(default_factory=list)
    failed_checks: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class BridgeAdaptationDecision(BaseModel):
    from_signature: str
    adaptation_kind: str
    new_components: List[BridgeComponent] = Field(default_factory=list)
    rationale: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class ReuseConstraints(BaseModel):
    same_host_fingerprint: bool = True
    same_program_hash: bool = True
    max_age_days: Optional[int] = None
    host_similarity_threshold: float = 1.0


class CompatibilityProfile(BaseModel):
    profile_id: str
    program_fingerprint: str
    program_hash: Optional[str] = None
    host_fingerprint: str
    program_kind: str = "unknown"
    gaps_resolved: List[CompatibilityGap] = Field(default_factory=list)
    bridge_plan: CompatibilityBridgePlan
    verification_contract: VerificationContract
    verification_result: VerificationResult
    winning_attempt: Optional[AttemptRecord] = None
    environment_identity: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    reuse_constraints: ReuseConstraints = Field(default_factory=ReuseConstraints)
    invalidation_conditions: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CompatibilityInspection(BaseModel):
    """Read-only compatibility analysis for a program on the current host."""

    schema_version: str = BRIDGE_DOMAIN_VERSION
    program: ProgramProfile
    host: HostCapabilityProfile
    wine_environment: Optional[WineEnvironmentProfile] = None
    gaps: List[CompatibilityGap] = Field(default_factory=list)
    blocker_count: int = 0
    major_count: int = 0
    ready_for_bridge: bool = False
    recommended_strategy_id: Optional[str] = None
    notes: List[str] = Field(default_factory=list)
