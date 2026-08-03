"""Pydantic models for compatibility intelligence analysis."""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

ACI_SCHEMA_VERSION = "compatibility_intelligence_v1"
ACI_CALIBRATION_SCHEMA_VERSION = "compatibility_intelligence_calibration_v1"
CAPABILITY_REGISTRY_VERSION = "aci_capability_registry_v1"


class ImplementationStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    DELEGATED = "delegated"
    EXPERIMENTAL = "experimental"
    UNKNOWN = "unknown"


class ConfidenceLevelName(str, Enum):
    VERY_HIGH = "very_high"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ApiComplexity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ProvenanceEvidence(BaseModel):
    source: str
    artifact_id: str
    digest: str = ""
    detail: str = ""

    @field_validator("source", "artifact_id")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("provenance requires non-empty source and artifact_id")
        return value.strip()


class ImportedFunction(BaseModel):
    dll: str
    name: str
    is_ordinal: bool = False


class ImportGraphEdge(BaseModel):
    source_dll: str
    target_dll: str
    functions: List[str] = Field(default_factory=list)


class SectionSummary(BaseModel):
    name: str
    virtual_size: int
    raw_size: int
    characteristics: int
    flags: List[str] = Field(default_factory=list)


class PeAnalysisMetadata(BaseModel):
    architecture: str
    subsystem: str
    entry_point_rva: int
    image_size: int
    is_pe32_plus: bool
    has_tls: bool
    has_relocations: bool
    has_clr: bool
    has_manifest: bool
    has_debug: bool
    has_load_config: bool
    has_exception_directory: bool
    export_count: int
    forwarded_exports: List[str] = Field(default_factory=list)
    sections: List[SectionSummary] = Field(default_factory=list)
    delay_import_dlls: List[str] = Field(default_factory=list)
    forwarded_imports: List[str] = Field(default_factory=list)
    resource_types: List[str] = Field(default_factory=list)


class ApiClassificationResult(BaseModel):
    dll: str
    function: str
    capability_id: str
    complexity: ApiComplexity
    native_status: ImplementationStatus
    wine_status: ImplementationStatus
    documentation_ref: str = ""
    is_known: bool = True
    provenance: ProvenanceEvidence


class CapabilityRequirement(BaseModel):
    capability_id: str
    description: str
    required_by_apis: List[str] = Field(default_factory=list)
    complexity: ApiComplexity = ApiComplexity.LOW


class ProviderCoverageBreakdown(BaseModel):
    provider_id: str
    supported: int = 0
    partial: int = 0
    unsupported: int = 0
    delegated: int = 0
    experimental: int = 0
    unknown: int = 0
    total: int = 0
    coverage_percent: float = 0.0
    blockers: List[str] = Field(default_factory=list)


class CoverageReport(BaseModel):
    total_capabilities: int
    total_apis: int
    known_apis: int
    unknown_apis: int
    providers: Dict[str, ProviderCoverageBreakdown] = Field(default_factory=dict)
    unsupported_api_names: List[str] = Field(default_factory=list)
    unknown_api_names: List[str] = Field(default_factory=list)


class ConfidenceAssessment(BaseModel):
    level: ConfidenceLevelName
    score: float = Field(ge=0.0, le=1.0)
    factors: List[str] = Field(default_factory=list)
    provenance: ProvenanceEvidence


class CompatibilityPrediction(BaseModel):
    native_compatible: bool
    wine_compatible: bool
    needs_unsupported_apis: bool
    confidence: ConfidenceAssessment
    potential_blockers: List[str] = Field(default_factory=list)
    recommended_provider_id: Optional[str] = None
    evidence_summary: str = ""


class GraphNode(BaseModel):
    node_id: str
    node_type: str
    label: str
    metadata: Dict[str, str] = Field(default_factory=dict)
    provenance: ProvenanceEvidence


class GraphEdge(BaseModel):
    edge_id: str
    source_id: str
    target_id: str
    relation: str
    provenance: ProvenanceEvidence


class CompatibilityGraph(BaseModel):
    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)


class RegistryMetrics(BaseModel):
    total_registry_apis: int
    classified_apis: int
    by_dll: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    capability_count: int
    native_supported_capabilities: int


class OutcomeType(str, Enum):
    VERIFIED_SUCCESS = "verified_success"
    VERIFIED_FAILURE = "verified_failure"
    UNVERIFIABLE = "unverifiable"
    EXECUTION_NOT_ATTEMPTED = "execution_not_attempted"
    PROVIDER_INELIGIBLE = "provider_ineligible"
    BLOCKED_BY_POLICY = "blocked_by_policy"
    RUNTIME_FAULT = "runtime_fault"
    VERIFICATION_INCONCLUSIVE = "verification_inconclusive"


class CalibrationClassification(str, Enum):
    TRUE_POSITIVE = "true_positive"
    FALSE_POSITIVE = "false_positive"
    TRUE_NEGATIVE = "true_negative"
    FALSE_NEGATIVE = "false_negative"
    INDETERMINATE = "indeterminate"


class FailureAttribution(str, Enum):
    UNSUPPORTED_DYNAMIC_IMPORT = "unsupported_dynamic_import"
    CAPABILITY_DECLARED_TOO_BROADLY = "capability_declared_too_broadly"
    API_SEMANTICS_INCOMPLETE = "API_semantics_incomplete"
    UNSUPPORTED_API_FLAG_OR_MODE = "unsupported_API_flag_or_mode"
    PROCESS_ENVIRONMENT_GAP = "process_environment_gap"
    LOADER_GAP = "loader_gap"
    ABI_GAP = "ABI_gap"
    FILESYSTEM_SEMANTICS_GAP = "filesystem_semantics_gap"
    SYNCHRONIZATION_GAP = "synchronization_gap"
    EXCEPTION_HANDLING_GAP = "exception_handling_gap"
    RESOURCE_OR_MANIFEST_GAP = "resource_or_manifest_gap"
    VERIFICATION_CONTRACT_MISMATCH = "verification_contract_mismatch"
    NON_RUNTIME_APPLICATION_FAILURE = "non_runtime_application_failure"
    UNKNOWN = "unknown"


class StaticCoverageSnapshot(BaseModel):
    """Symbol/capability coverage at prediction time — not verified compatibility."""

    symbol_coverage_percent: float = 0.0
    capability_coverage_percent: float = 0.0
    behavior_coverage_percent: float = 0.0
    verified_scenario_coverage_percent: float = 0.0
    unknown_api_count: int = 0
    unresolved_dynamic_behavior_count: int = 0
    behavior_gaps: List[str] = Field(default_factory=list)
    providers: Dict[str, ProviderCoverageBreakdown] = Field(default_factory=dict)


class PredictionSnapshot(BaseModel):
    """Immutable pre-execution prediction bound to exact binary and registry versions."""

    schema_version: str = ACI_CALIBRATION_SCHEMA_VERSION
    snapshot_id: str
    session_id: str = ""
    analysis_digest: str
    binary_digest: str
    provider_id: str
    provider_version: str
    capability_registry_version: str
    api_registry_version: str
    required_capabilities: List[str] = Field(default_factory=list)
    unsupported_capabilities: List[str] = Field(default_factory=list)
    unknown_apis: List[str] = Field(default_factory=list)
    delegated_capabilities: List[str] = Field(default_factory=list)
    static_coverage: StaticCoverageSnapshot
    confidence_level: ConfidenceLevelName
    confidence_score: float = Field(ge=0.0, le=1.0)
    blockers: List[str] = Field(default_factory=list)
    prediction: CompatibilityPrediction
    predicted_eligible: bool = False
    created_at: str
    engine_version: str


class OutcomeLink(BaseModel):
    """Links a prediction snapshot to an authoritative verification outcome."""

    schema_version: str = ACI_CALIBRATION_SCHEMA_VERSION
    outcome_id: str
    snapshot_id: str
    session_id: str
    attempt_id: Optional[int] = None
    binary_digest: str
    analysis_digest: str
    provider_id: str
    provider_version: str
    capability_snapshot_digest: str = ""
    outcome_type: OutcomeType
    verification_result_ref: Optional[str] = None
    predicted_eligible: bool = False
    verified_success: bool = False
    failure_signature: Optional[str] = None
    created_at: str
    engine_version: str


class CompatibilityAnalysisResult(BaseModel):
    schema_version: str = ACI_SCHEMA_VERSION
    analysis_id: str
    file_path: str
    binary_digest: str
    metadata: PeAnalysisMetadata
    imports: List[ImportedFunction] = Field(default_factory=list)
    import_graph: List[ImportGraphEdge] = Field(default_factory=list)
    api_classifications: List[ApiClassificationResult] = Field(default_factory=list)
    required_capabilities: List[CapabilityRequirement] = Field(default_factory=list)
    coverage: CoverageReport
    prediction: CompatibilityPrediction
    graph: CompatibilityGraph
    provenance: ProvenanceEvidence
