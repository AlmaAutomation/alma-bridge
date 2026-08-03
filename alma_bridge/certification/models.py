"""Runtime Certification Platform models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

CERTIFICATION_SCHEMA_VERSION = "certification_v1"
CERTIFICATION_ENGINE_VERSION = "certification_service_v1"
CERTIFICATION_PROVIDER_ID = "native_alma"
CERTIFICATION_IMPLEMENTATION_VERSION = "0.2.0-m2"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class CertificationLevel(str, Enum):
    UNVERIFIED = "unverified"
    SPECIFIED = "specified"
    BEHAVIOR_TESTED = "behavior_tested"
    VERIFIED = "verified"
    CALIBRATED = "calibrated"
    GOVERNED = "governed"
    CERTIFIED = "certified"
    PRODUCTION_READY = "production_ready"
    REQUIRES_REVALIDATION = "requires_revalidation"


class ComplianceStatus(str, Enum):
    NOT_CERTIFIED = "not_certified"
    IN_PROGRESS = "in_progress"
    CERTIFIED = "certified"
    UNSUPPORTED = "unsupported"
    REQUIRES_REVALIDATION = "requires_revalidation"


class StaleReason(str, Enum):
    BEHAVIOR_REGRESSION = "behavior_regression"
    ABI_CHANGE = "abi_change"
    BENCHMARK_DEGRADATION = "benchmark_degradation"
    FAILED_VERIFICATION = "failed_verification"
    PROVIDER_CHANGE = "provider_change"
    REGISTRY_CHANGE = "registry_change"


class SpecificationLink(BaseModel):
    api_symbol: str
    spec_digest: str = ""
    supported: bool = True
    limitations: List[str] = Field(default_factory=list)


class BehaviorSuiteLink(BaseModel):
    suite_id: str
    case_ids: List[str] = Field(default_factory=list)
    fixture_paths: List[str] = Field(default_factory=list)
    test_status: str = "pending"


class CalibrationHistoryLink(BaseModel):
    snapshot_id: str
    binary_digest: str = ""
    recorded_at: str = ""


class GovernanceHistoryLink(BaseModel):
    capability_id: str
    maturity_state: str = ""
    registry_version: str = ""


class BenchmarkHistoryLink(BaseModel):
    benchmark_id: str
    run_digest: str = ""
    recorded_at: str = ""


class ResearchReferenceLink(BaseModel):
    reference_id: str
    source: str = "research"
    digest: str = ""


class EvidenceReferenceLink(BaseModel):
    source: str
    artifact_id: str
    digest: str = ""
    fixture_path: Optional[str] = None


class TimelineReferenceLink(BaseModel):
    timeline_id: str
    event_type: str = ""
    recorded_at: str = ""


class VerificationContractLink(BaseModel):
    check_id: str
    category: str = ""
    status: str = "pending"


class BehaviorCertification(BaseModel):
    capability_id: str
    behavior_id: str
    api_symbols: List[str] = Field(default_factory=list)
    supported: bool = True
    certification_level: CertificationLevel = CertificationLevel.UNVERIFIED
    compliance_status: ComplianceStatus = ComplianceStatus.NOT_CERTIFIED
    specification: Optional[SpecificationLink] = None
    behavior_suite: Optional[BehaviorSuiteLink] = None
    verification_contracts: List[VerificationContractLink] = Field(default_factory=list)
    calibration_history: List[CalibrationHistoryLink] = Field(default_factory=list)
    governance_history: List[GovernanceHistoryLink] = Field(default_factory=list)
    benchmark_history: List[BenchmarkHistoryLink] = Field(default_factory=list)
    research_references: List[ResearchReferenceLink] = Field(default_factory=list)
    evidence_references: List[EvidenceReferenceLink] = Field(default_factory=list)
    timeline_references: List[TimelineReferenceLink] = Field(default_factory=list)
    known_limitations: List[str] = Field(default_factory=list)
    fixture_coverage_pct: float = 0.0
    verification_pct: float = 0.0
    evidence_count: int = 0
    regression_status: str = "none"
    governance_level: str = ""
    stale_reasons: List[StaleReason] = Field(default_factory=list)
    stale_detail: str = ""
    certification_digest: str = ""
    computed_at: str = Field(default_factory=utc_now_iso)
    provider_id: str = CERTIFICATION_PROVIDER_ID
    implementation_version: str = CERTIFICATION_IMPLEMENTATION_VERSION


class ComplianceMatrixEntry(BaseModel):
    api_symbol: str
    behavior_id: str
    capability_id: str
    status: ComplianceStatus
    coverage_pct: float = 0.0
    evidence_count: int = 0
    verification_pct: float = 0.0
    regression_status: str = "none"
    governance_level: str = ""
    certification_level: CertificationLevel = CertificationLevel.UNVERIFIED
    supported: bool = True
    limitations: List[str] = Field(default_factory=list)


class ComplianceMatrix(BaseModel):
    generated_at: str = Field(default_factory=utc_now_iso)
    schema_version: str = CERTIFICATION_SCHEMA_VERSION
    provider_id: str = CERTIFICATION_PROVIDER_ID
    entries: List[ComplianceMatrixEntry] = Field(default_factory=list)
    matrix_digest: str = ""


class CertificationRecord(BaseModel):
    record_id: str
    capability_id: str
    behavior_id: str
    previous_level: Optional[CertificationLevel] = None
    new_level: CertificationLevel
    transition_reason: str = ""
    evidence_references: List[EvidenceReferenceLink] = Field(default_factory=list)
    spec_digest: str = ""
    recorded_at: str = Field(default_factory=utc_now_iso)
    record_digest: str = ""


class CertificationHistory(BaseModel):
    capability_id: str
    behavior_id: str
    records: List[CertificationRecord] = Field(default_factory=list)
    history_digest: str = ""


class StaleCertificationItem(BaseModel):
    capability_id: str
    behavior_id: str
    previous_level: CertificationLevel
    stale_reasons: List[StaleReason] = Field(default_factory=list)
    detail: str = ""
    detected_at: str = Field(default_factory=utc_now_iso)


class CertificationDashboard(BaseModel):
    generated_at: str = Field(default_factory=utc_now_iso)
    schema_version: str = CERTIFICATION_SCHEMA_VERSION
    provider_id: str = CERTIFICATION_PROVIDER_ID
    implementation_version: str = CERTIFICATION_IMPLEMENTATION_VERSION
    behavior_count: int = 0
    certified_count: int = 0
    stale_count: int = 0
    unsupported_count: int = 0
    compliance_matrix: ComplianceMatrix
    stale_items: List[StaleCertificationItem] = Field(default_factory=list)
    certifications_summary: List[Dict[str, Any]] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
