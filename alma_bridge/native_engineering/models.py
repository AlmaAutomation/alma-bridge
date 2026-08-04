"""Native Runtime Engineering Platform models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

NATIVE_ENGINEERING_SCHEMA_VERSION = "native_engineering_v1"
NATIVE_ENGINEERING_ENGINE_VERSION = "native_engineering_service_v1"
NATIVE_PROVIDER_ID = "native_alma"
NATIVE_IMPLEMENTATION_VERSION = "0.2.0-m2"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class TestScenarioStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    PENDING = "pending"
    NOT_APPLICABLE = "not_applicable"
    DEFERRED = "deferred"


class ValidationCategory(str, Enum):
    API_SEMANTIC = "api_semantic"
    MEMORY = "memory"
    HANDLE_LIFECYCLE = "handle_lifecycle"
    FILESYSTEM = "filesystem"
    UNICODE = "unicode"
    THREADING = "threading"


class ParameterSpec(BaseModel):
    name: str
    type_name: str
    description: str = ""
    nullable: bool = False


class ErrorMode(BaseModel):
    condition: str
    error_code: Optional[int] = None
    error_name: str = ""
    return_value: Optional[str] = None


class ApiSpecification(BaseModel):
    api_symbol: str
    dll: str = "kernel32.dll"
    calling_convention: str = "ms_abi"
    parameters: List[ParameterSpec] = Field(default_factory=list)
    return_type: str = "BOOL"
    success_semantics: str = ""
    error_modes: List[ErrorMode] = Field(default_factory=list)
    supported_behaviors: List[str] = Field(default_factory=list)
    unsupported_behaviors: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    spec_digest: str = ""


class BehaviorTestCase(BaseModel):
    case_id: str
    description: str
    expected_outcome: str
    fixture_path: Optional[str] = None
    status: TestScenarioStatus = TestScenarioStatus.PENDING
    behavior_id: str = ""


class BehaviorTestSuite(BaseModel):
    api_symbol: str
    suite_id: str
    cases: List[BehaviorTestCase] = Field(default_factory=list)
    coverage_summary: str = ""


class BenchmarkMetric(BaseModel):
    name: str
    value: float
    unit: str = "ms"
    tolerance_percent: float = 10.0


class BenchmarkBaselineStats(BaseModel):
    warmup_count: int = 3
    iteration_count: int = 10
    median_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    mean_ms: float = 0.0
    stddev_ms: float = 0.0
    mad_ms: float = 0.0
    sample_size: int = 0


class BenchmarkHostEnvironment(BaseModel):
    host_arch: str = ""
    cpu_model: str = ""
    kernel_version: str = ""
    compiler: str = ""
    shim_version: str = ""
    fixture_digest: str = ""
    workspace_type: str = "isolated_tmp"


class BenchmarkResult(BaseModel):
    benchmark_id: str
    fixture_name: str
    api_symbol: str = ""
    metrics: List[BenchmarkMetric] = Field(default_factory=list)
    baseline: Optional[BenchmarkBaselineStats] = None
    host_environment: Optional[BenchmarkHostEnvironment] = None
    exit_code: Optional[int] = None
    output_verified: bool = False
    recorded_at: str = Field(default_factory=utc_now_iso)
    run_digest: str = ""
    engine_version: str = NATIVE_ENGINEERING_ENGINE_VERSION


class ConformanceCheck(BaseModel):
    check_id: str
    category: str
    description: str
    status: TestScenarioStatus
    detail: str = ""


class ConformanceReport(BaseModel):
    report_id: str
    provider_id: str = NATIVE_PROVIDER_ID
    implementation_version: str = NATIVE_IMPLEMENTATION_VERSION
    checks: List[ConformanceCheck] = Field(default_factory=list)
    generated_at: str = Field(default_factory=utc_now_iso)
    report_digest: str = ""


class ValidationResult(BaseModel):
    category: ValidationCategory
    api_symbol: str
    check_id: str
    status: TestScenarioStatus
    message: str = ""


class CalibrationLink(BaseModel):
    snapshot_id: str
    classification: str = ""
    binary_digest: str = ""
    recorded_at: str = ""


class GovernanceLink(BaseModel):
    capability_id: str
    maturity_state: str = ""
    scope_key: str = ""
    registry_version: str = ""


class EvidenceLink(BaseModel):
    source: str
    artifact_id: str
    digest: str = ""
    fixture_path: Optional[str] = None


class ApiEngineeringProfile(BaseModel):
    api_symbol: str
    capability_id: str
    behavior_ids: List[str] = Field(default_factory=list)
    specification: ApiSpecification
    behavior_suite: BehaviorTestSuite
    calibration_links: List[CalibrationLink] = Field(default_factory=list)
    governance_links: List[GovernanceLink] = Field(default_factory=list)
    benchmark_results: List[BenchmarkResult] = Field(default_factory=list)
    evidence_links: List[EvidenceLink] = Field(default_factory=list)
    validation_results: List[ValidationResult] = Field(default_factory=list)
    profile_digest: str = ""


class BehaviorCoverageEntry(BaseModel):
    behavior_id: str
    capability_id: str
    api_symbols: List[str] = Field(default_factory=list)
    supported: bool = True
    test_status: TestScenarioStatus = TestScenarioStatus.PENDING
    fixture_paths: List[str] = Field(default_factory=list)


class BehaviorCoverageDashboard(BaseModel):
    generated_at: str = Field(default_factory=utc_now_iso)
    provider_id: str = NATIVE_PROVIDER_ID
    entries: List[BehaviorCoverageEntry] = Field(default_factory=list)
    unsupported_behaviors: List[str] = Field(default_factory=list)


class LongitudinalPoint(BaseModel):
    timestamp: str
    benchmark_id: str
    metric_name: str
    value: float
    run_digest: str = ""


class BenchmarkHistory(BaseModel):
    benchmark_id: str
    points: List[LongitudinalPoint] = Field(default_factory=list)


class EngineeringDashboard(BaseModel):
    generated_at: str = Field(default_factory=utc_now_iso)
    schema_version: str = NATIVE_ENGINEERING_SCHEMA_VERSION
    provider_id: str = NATIVE_PROVIDER_ID
    implementation_version: str = NATIVE_IMPLEMENTATION_VERSION
    api_count: int = 0
    behavior_coverage: BehaviorCoverageDashboard
    conformance_report: ConformanceReport
    benchmark_history: List[BenchmarkHistory] = Field(default_factory=list)
    profiles_summary: List[Dict[str, Any]] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
