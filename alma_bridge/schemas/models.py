from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, computed_field


class RuntimeKind(str, Enum):
    NATIVE = "native"
    WINE = "wine"
    PROTON = "proton"
    QEMU_USER = "qemu_user"
    CONTAINER = "container"
    MULTIARCH = "multiarch"


class ExecutionMode(str, Enum):
    HOST = "host"
    CONTAINER = "container"


class BridgeRequest(BaseModel):
    file_path: str
    args: List[str] = Field(default_factory=list)
    runtime_hint: Optional[RuntimeKind] = None
    preferred_strategy_id: Optional[str] = None
    preferred_remediation_id: Optional[str] = None
    wine_prefix: Optional[str] = None
    proton_path: Optional[str] = None
    env: Dict[str, str] = Field(default_factory=dict)
    sandbox: bool = False
    use_sudo: bool = False
    sudo_password: Optional[str] = None
    max_attempts: Optional[int] = None
    launch_after_install: bool = True
    auto_remediate: Optional[bool] = None
    shadow_host_payload_overlay: Optional[Dict[str, Any]] = None


class AttemptRecord(BaseModel):
    attempt_number: int
    strategy_id: str
    remediation_id: Optional[str] = None
    runtime: str
    command: List[str]
    env: Dict[str, str] = Field(default_factory=dict)
    mode: ExecutionMode
    success: bool
    exit_code: Optional[int] = None
    error_signature: Optional[str] = None
    detected_error: Optional[str] = None
    suggested_fix: Optional[str] = None
    recommended_actions: List[str] = Field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    phase: str = "run"


class ProgramPreflightResponse(BaseModel):
    file_path: str
    exists: bool = False
    binary_format: str = "unknown"
    program_kind: str = "unknown"
    profile: str = "generic"
    is_installer: bool = False
    is_electron: bool = False
    is_launcher: bool = False
    needs_wine: bool = False
    needs_gui: bool = False
    needs_native: bool = False
    ready: bool = False
    display: Optional[str] = None
    wine_available: bool = False
    wine_path: Optional[str] = None
    suggested_wine_prefix: Optional[str] = None
    prefix_exists: bool = False
    prefix_writable: bool = False
    known_prefixes: List[Dict[str, Any]] = Field(default_factory=list)
    blockers: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    recommended_runtime: str = "native"
    recommended_max_attempts: int = 8
    recommended_args: List[str] = Field(default_factory=list)
    recommended_remediation_id: Optional[str] = None
    installed_launcher_path: Optional[str] = None


class LauncherPreflightResponse(BaseModel):
    file_path: str
    is_launcher: bool = False
    is_ascension: bool = False
    profile: str = "generic"
    ready: bool = False
    display: Optional[str] = None
    wine_available: bool = False
    wine_path: Optional[str] = None
    suggested_wine_prefix: Optional[str] = None
    prefix_exists: bool = False
    prefix_writable: bool = False
    known_prefixes: List[Dict[str, Any]] = Field(default_factory=list)
    blockers: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    recommended_runtime: str = "wine"
    recommended_max_attempts: int = 12
    recommended_args: List[str] = Field(default_factory=list)
    recommended_remediation_id: Optional[str] = None


class InstallerPreflightResponse(BaseModel):
    file_path: str
    is_installer: bool = False
    ready: bool = False
    display: Optional[str] = None
    wine_available: bool = False
    wine_path: Optional[str] = None
    suggested_wine_prefix: Optional[str] = None
    prefix_exists: bool = False
    prefix_writable: bool = False
    known_prefixes: List[Dict[str, Any]] = Field(default_factory=list)
    blockers: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    recommended_runtime: str = "wine"
    recommended_max_attempts: int = 12
    recommended_args: List[str] = Field(default_factory=list)


class RerankEvent(BaseModel):
    sequence: int
    after_strategy_id: str
    error_signature: Optional[str] = None
    previous_order: List[str] = Field(default_factory=list)
    new_order: List[str] = Field(default_factory=list)
    order_changed: bool = False
    top_pick: Optional[str] = None
    top_success_probability: Optional[float] = None
    rank_source: Optional[str] = None


class BridgeRunStartedResponse(BaseModel):
    session_id: str
    status: str = "running"


class BridgeSessionResult(BaseModel):
    session_id: str
    file_path: str
    file_hash: Optional[str] = None
    started_at: datetime
    finished_at: datetime
    success: bool
    winning_attempt: Optional[AttemptRecord] = None
    attempts: List[AttemptRecord] = Field(default_factory=list)
    hardware_profile: Dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    recommended_actions: List[str] = Field(default_factory=list)
    rerank_events: List[RerankEvent] = Field(default_factory=list)
    installed_launcher_path: Optional[str] = None
    skipped_installer: bool = False


class HardwareProfileResponse(BaseModel):
    profile: Dict[str, Any]
    shims_available: List[Dict[str, Any]] = Field(default_factory=list)
    capabilities: Dict[str, bool] = Field(default_factory=dict)


class OutcomeStatsResponse(BaseModel):
    total_attempts: int
    total_successes: int
    total_failures: int
    success_rate: float
    top_signatures: List[Dict[str, Any]] = Field(default_factory=list)
    top_strategies: List[Dict[str, Any]] = Field(default_factory=list)


class PriorSuccessResponse(BaseModel):
    file_path: str
    found: bool
    session_id: Optional[str] = None
    finished_at: Optional[str] = None
    strategy_id: Optional[str] = None
    remediation_id: Optional[str] = None
    runtime: Optional[str] = None
    total_sessions: int = 0
    successful_sessions: int = 0
    success_rate_for_path: float = 0.0


class RecentSessionItem(BaseModel):
    session_id: str
    application_fingerprint: Optional[str] = None
    application_name: str
    state: str
    verified: bool
    started_at: str
    finished_at: Optional[str] = None
    graph_compatible: bool = False


class RecentSessionsResponse(BaseModel):
    sessions: List[RecentSessionItem] = Field(default_factory=list)
    count: int = 0


class ImportRequest(BaseModel):
    sysdet_db: Optional[str] = None
    resolve_audit_dir: Optional[str] = None
    limit: Optional[int] = None
    skip_existing: bool = True
    sources: List[str] = Field(default_factory=lambda: ["almasysdet", "alma_resolve"])


class ImportResult(BaseModel):
    almasysdet: Optional[Dict[str, Any]] = None
    alma_resolve: Optional[Dict[str, Any]] = None
    total_sessions: int = 0
    total_attempts: int = 0


class TrainRankerResult(BaseModel):
    trained: bool
    records: int = 0
    successes: int = 0
    failures: int = 0
    metrics: Dict[str, Any] = Field(default_factory=dict)
    strategy_success_rates: Dict[str, Any] = Field(default_factory=dict)
    model_path: Optional[str] = None
    reason: Optional[str] = None


class TlsAssessRequest(BaseModel):
    host: str
    port: int = 443
    timeout: float = 6.0
    probe_legacy: bool = True


class TlsPostureResponse(BaseModel):
    host: str
    port: int
    compliant: bool
    reachable: bool
    grade: str
    blockers: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    recommendation: Optional[str] = None
    observation: Dict[str, Any] = Field(default_factory=dict)


class TlsBridgeStartRequest(BaseModel):
    upstream_host: str
    upstream_port: int = 443
    listen_host: str = "127.0.0.1"
    listen_port: int = 0
    verify: bool = True
    upstream_sni: Optional[str] = None
    min_tls: str = "TLSv1.2"


class TlsBridgeInfo(BaseModel):
    id: str
    listen: str
    upstream: str
    verify: bool
    upstream_sni: Optional[str] = None
    min_tls: str
    created_at: str
    active_connections: int = 0
    total_connections: int = 0
    bytes_up: int = 0
    bytes_down: int = 0
    last_error: Optional[str] = None


class TlsBridgeListResponse(BaseModel):
    bridges: List[TlsBridgeInfo] = Field(default_factory=list)
    count: int = 0


class DriverInventoryResponse(BaseModel):
    device_count: int
    bound_count: int
    missing_driver_count: int
    devices: List[Dict[str, Any]] = Field(default_factory=list)
    missing_drivers: List[Dict[str, Any]] = Field(default_factory=list)
    compliant: bool


class ComplianceScanRequest(BaseModel):
    targets: List[str] = Field(default_factory=list)
    include_drivers: bool = True
    include_shims: bool = True
    tls_timeout: float = 6.0
    probe_legacy: bool = True
    web3_rpc: List[str] = Field(default_factory=list)
    check_time: bool = True
    ntp_server: str = "pool.ntp.org"
    scan_services: bool = False


class ComplianceReportResponse(BaseModel):
    generated_at: str
    overall_compliant: bool
    summary: Dict[str, Any] = Field(default_factory=dict)
    host: Dict[str, Any] = Field(default_factory=dict)
    tls: List[Dict[str, Any]] = Field(default_factory=list)
    web3: List[Dict[str, Any]] = Field(default_factory=list)
    clock: Optional[Dict[str, Any]] = None
    services: List[Dict[str, Any]] = Field(default_factory=list)
    drivers: Optional[Dict[str, Any]] = None
    recommended_shims: List[Dict[str, Any]] = Field(default_factory=list)
    remediations: List[Dict[str, Any]] = Field(default_factory=list)


class ClockCheckRequest(BaseModel):
    ntp_server: str = "pool.ntp.org"
    timeout: float = 5.0


class ClockPostureResponse(BaseModel):
    compliant: Optional[bool] = None
    skew_seconds: Optional[float] = None
    severity: str
    impact: str
    ntp_server: Optional[str] = None
    local_epoch: Optional[float] = None
    reference_epoch: Optional[float] = None


class ServiceScanRequest(BaseModel):
    host: str
    ports: Optional[List[int]] = None
    timeout: float = 2.0


class ServiceScanResponse(BaseModel):
    host: str
    scanned_ports: int
    insecure_count: int
    findings: List[Dict[str, Any]] = Field(default_factory=list)
    compliant: bool


class DohResolveRequest(BaseModel):
    name: str
    record_type: str = "A"
    provider: str = "cloudflare"
    timeout: float = 6.0


class DohResolveResponse(BaseModel):
    ok: bool
    status: Optional[int] = None
    rcode: Optional[Any] = None
    answers: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
    provider: Optional[str] = None
    query: Optional[Dict[str, Any]] = None


class Web3AssessRequest(BaseModel):
    rpc_url: str
    timeout: float = 8.0
    check_tls: bool = True


class Web3PostureResponse(BaseModel):
    url: str
    web3_ready: bool
    chain: Dict[str, Any] = Field(default_factory=dict)
    client_version: Optional[str] = None
    latency_ms: Optional[float] = None
    blockers: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    recommendation: Optional[str] = None
    tls: Optional[Dict[str, Any]] = None
    observation: Dict[str, Any] = Field(default_factory=dict)


class IpfsUrlRequest(BaseModel):
    uri: str
    gateway: str = "https://ipfs.io"


class IpfsUrlResponse(BaseModel):
    url: Optional[str] = None
    scheme: Optional[str] = None
    cid: Optional[str] = None
    valid_cid: bool = False
    error: Optional[str] = None


class Web3ChainsResponse(BaseModel):
    chains: Dict[int, Dict[str, str]] = Field(default_factory=dict)
    count: int = 0


# --------------------------------------------------------------------------- #
# Self-healing autopilot
# --------------------------------------------------------------------------- #


class AutopilotRequest(BaseModel):
    error_text: str
    binary: Optional[str] = None
    os_release: Optional[str] = None
    execute: bool = False
    allow_mutations: bool = False
    timeout: float = 8.0
    sudo_password: Optional[str] = None


class AutopilotResponse(BaseModel):
    package_manager: str
    primary_signature: str
    diagnoses: List[Dict[str, Any]] = Field(default_factory=list)
    pathways: List[Dict[str, Any]] = Field(default_factory=list)
    executed_diagnostics: List[Dict[str, Any]] = Field(default_factory=list)
    executed_remediations: List[Dict[str, Any]] = Field(default_factory=list)
    mutations_applied: bool = False


class AutopilotDiagnoseResponse(BaseModel):
    diagnoses: List[Dict[str, Any]] = Field(default_factory=list)


class AutopilotFeedbackRequest(BaseModel):
    signature: str
    pathway_id: str
    success: bool


class AutopilotFeedbackResponse(BaseModel):
    recorded: bool
    summary: List[Dict[str, Any]] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# 32-bit legacy readiness
# --------------------------------------------------------------------------- #


class Legacy32Response(BaseModel):
    ready: bool
    verdict: str
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    gaps: List[str] = Field(default_factory=list)
    notes: str = ""


class Legacy32PlanRequest(BaseModel):
    os_release: Optional[str] = None


class Legacy32PlanResponse(BaseModel):
    package_manager: str
    ready: bool
    gaps: List[str] = Field(default_factory=list)
    steps: List[Dict[str, Any]] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Legacy host modernization (assess + playbook + apply)
# --------------------------------------------------------------------------- #


class ModernizationAssessResponse(BaseModel):
    verdict: str
    potato_score: int = 0
    package_manager: str = ""
    hardware: Dict[str, Any] = Field(default_factory=dict)
    glibc_version: Optional[str] = None
    disk_free_gb: Optional[float] = None
    swappiness: Optional[int] = None
    zram_available: bool = False
    ca_store: Dict[str, Any] = Field(default_factory=dict)
    legacy32: Dict[str, Any] = Field(default_factory=dict)
    browsers: Dict[str, Any] = Field(default_factory=dict)
    browser_recommendation: Dict[str, Any] = Field(default_factory=dict)
    gaps: List[str] = Field(default_factory=list)
    summary: str = ""

    @computed_field
    @property
    def lab_readiness_score(self) -> int:
        return self.potato_score


class ModernizationPlaybookRequest(BaseModel):
    os_release: Optional[str] = None
    include_browser: bool = True
    include_potato_tuning: bool = True


class ModernizationPlaybookResponse(BaseModel):
    verdict: str
    potato_score: int = 0
    package_manager: str = ""
    gaps: List[str] = Field(default_factory=list)
    summary: str = ""
    browser_recommendation: Dict[str, Any] = Field(default_factory=dict)
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    apply_step_ids: List[str] = Field(default_factory=list)

    @computed_field
    @property
    def lab_readiness_score(self) -> int:
        return self.potato_score


class ModernizationApplyRequest(BaseModel):
    step_ids: Optional[List[str]] = None
    allow_mutations: bool = False
    stop_on_error: bool = True
    os_release: Optional[str] = None
    include_browser: bool = True
    include_potato_tuning: bool = True
    sudo_password: Optional[str] = None


class ModernizationApplyResponse(BaseModel):
    applied: bool
    success: bool = False
    reason: Optional[str] = None
    results: List[Dict[str, Any]] = Field(default_factory=list)
    playbook_verdict: Optional[str] = None


class WindowsModernizationAssessResponse(BaseModel):
    host_platform: str
    can_apply_locally: bool = False
    verdict: str
    potato_score: int = 0
    gaps: List[str] = Field(default_factory=list)
    summary: str = ""
    hardware: Dict[str, Any] = Field(default_factory=dict)
    os: Dict[str, Any] = Field(default_factory=dict)
    browsers: Dict[str, Any] = Field(default_factory=dict)
    time_service_ok: Optional[bool] = None
    planning_only: bool = False

    @computed_field
    @property
    def lab_readiness_score(self) -> int:
        return self.potato_score


class WindowsModernizationPlaybookRequest(BaseModel):
    recipe_id: str = "school-lab-windows"
    include_browser: bool = True
    include_performance_tuning: bool = True


class WindowsModernizationPlaybookResponse(BaseModel):
    verdict: str
    potato_score: int = 0
    gaps: List[str] = Field(default_factory=list)
    summary: str = ""
    host_platform: str = "windows"
    can_apply_locally: bool = False
    planning_only: bool = False
    browser_recommendation: Dict[str, Any] = Field(default_factory=dict)
    recipe_id: str = "school-lab-windows"
    recipe_title: str = ""
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    apply_step_ids: List[str] = Field(default_factory=list)
    export_script: str = ""

    @computed_field
    @property
    def lab_readiness_score(self) -> int:
        return self.potato_score


class WindowsModernizationApplyRequest(BaseModel):
    step_ids: Optional[List[str]] = None
    allow_mutations: bool = False
    stop_on_error: bool = True
    recipe_id: str = "school-lab-windows"
    include_browser: bool = True
    include_performance_tuning: bool = True


class WindowsModernizationApplyResponse(BaseModel):
    applied: bool
    success: bool = False
    reason: Optional[str] = None
    results: List[Dict[str, Any]] = Field(default_factory=list)
    export_script: str = ""
    playbook_verdict: Optional[str] = None


# --------------------------------------------------------------------------- #
# Automation platform (unified scan → modernize → verify → learn)
# --------------------------------------------------------------------------- #


class AutomationRunRequest(BaseModel):
    scan_path: Optional[str] = None
    playbook_recipe: Optional[str] = None
    apply: bool = False
    allow_mutations: bool = False
    approval_token: Optional[str] = None
    sudo_password: Optional[str] = None
    step_ids: Optional[List[str]] = None
    verify: bool = True
    https_probe_host: str = "example.com"
    file_path: Optional[str] = None
    bridge_run: bool = False
    bridge_max_attempts: int = 4
    bridge_sandbox: bool = False
    error_text: Optional[str] = None
    os_release: Optional[str] = None
    container_run: bool = False


class AutomationRunResponse(BaseModel):
    session_id: str
    success: bool
    summary: str
    phases: List[Dict[str, Any]] = Field(default_factory=list)
    health: Dict[str, Any] = Field(default_factory=dict)


class AutomationHealthResponse(BaseModel):
    hostname: str
    machine: str
    verdict: Optional[str] = None
    potato_score: Optional[int] = None
    gaps: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    browsers: Optional[Dict[str, Any]] = None
    browser_recommendation: Optional[Dict[str, Any]] = None
    hardware: Optional[Dict[str, Any]] = None
    last_automation: Optional[Dict[str, Any]] = None
    recent_sessions: List[Dict[str, Any]] = Field(default_factory=list)

    @computed_field
    @property
    def lab_readiness_score(self) -> Optional[int]:
        return self.potato_score


class AutomationApprovalRequest(BaseModel):
    step_ids: List[str]
    ttl_minutes: int = 30


class AutomationApprovalResponse(BaseModel):
    token: str
    step_ids: List[str]
    expires_at: str
    ttl_minutes: int


class AutomationPlaybooksResponse(BaseModel):
    playbooks: List[Dict[str, Any]] = Field(default_factory=list)


class AutomationAgentRegisterRequest(BaseModel):
    agent_id: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


class AutomationAgentRegisterResponse(BaseModel):
    agent_id: str
    hostname: str
    capabilities: Dict[str, Any] = Field(default_factory=dict)


class AutomationAgentHeartbeatRequest(BaseModel):
    agent_id: str


class AutomationAgentRunRequest(BaseModel):
    agent_id: str
    scan_path: Optional[str] = None
    playbook_recipe: Optional[str] = None
    apply: bool = False
    allow_mutations: bool = False
    approval_token: Optional[str] = None
    sudo_password: Optional[str] = None
    step_ids: Optional[List[str]] = None
    verify: bool = True
    os_release: Optional[str] = None
    error_text: Optional[str] = None
    container_run: bool = False


# --------------------------------------------------------------------------- #
# AI Operator (autonomous observe → decide → apply → verify)
# --------------------------------------------------------------------------- #


class OperatorPlanRequest(BaseModel):
    os_release: Optional[str] = None
    error_text: Optional[str] = None


class OperatorTickRequest(BaseModel):
    apply: bool = False
    sudo_password: Optional[str] = None


class OperatorRemediateRequest(BaseModel):
    apply: bool = False
    sudo_password: Optional[str] = None
    only_auto: bool = False
    limit: int = 10


class SudoWarmRequest(BaseModel):
    sudo_password: Optional[str] = None


class MakeWorkRequest(BaseModel):
    """Build host + Bridge compatibility until a program can run."""

    file_path: str
    error_text: Optional[str] = None
    apply: bool = True
    sudo_password: Optional[str] = None


class OperatorStartRequest(BaseModel):
    interval_sec: Optional[int] = None
    apply: bool = False


# --------------------------------------------------------------------------- #
# Container shim pack (VM-like isolated execution)
# --------------------------------------------------------------------------- #


class SandboxStatusResponse(BaseModel):
    ready: bool
    runtime: Optional[str] = None
    image: str
    sandbox_enabled: bool
    shim_count: int = 0


class ContainerShimPackRequest(BaseModel):
    file_path: str
    shim_ids: Optional[List[str]] = None
    error_signature: Optional[str] = None
    extra_env: Optional[Dict[str, str]] = None
    sandbox_image: Optional[str] = None
    use_sudo: bool = False


class ContainerShimPackResponse(BaseModel):
    ok: bool
    error: Optional[str] = None
    file_path: Optional[str] = None
    binary_format: Optional[str] = None
    program_kind: Optional[str] = None
    host_architecture: Optional[str] = None
    sandbox_ready: Optional[bool] = None
    runtime: Optional[str] = None
    image: Optional[str] = None
    shims: List[Dict[str, Any]] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    command: List[str] = Field(default_factory=list)
    container_spec: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    hardware_summary: Optional[Dict[str, Any]] = None


class ContainerRunRequest(ContainerShimPackRequest):
    timeout_sec: Optional[int] = None
    extra_args: Optional[List[str]] = None


class ContainerRunResponse(ContainerShimPackResponse):
    executed: bool = False
    success: bool = False
    exit_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
