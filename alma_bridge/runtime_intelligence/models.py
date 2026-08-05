"""Domain models for Runtime Intelligence."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Mapping, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.research.models import SampleSize

RUNTIME_INTELLIGENCE_SCHEMA_VERSION = "runtime_intelligence_corpus_v1"
RUNTIME_INTELLIGENCE_INDEX_SCHEMA_VERSION = "runtime_intelligence_index_v1"
RUNTIME_INTELLIGENCE_KNOWLEDGE_SCHEMA_VERSION = "runtime_intelligence_knowledge_v1"
RUNTIME_INTELLIGENCE_DEBT_SCHEMA_VERSION = "runtime_intelligence_debt_v1"
COMPATIBILITY_INDEX_FORMULA_VERSION = "compatibility_index_v1"
KNOWLEDGE_COVERAGE_FORMULA_VERSION = "knowledge_coverage_v1"
DEBT_CLASSIFICATION_FORMULA_VERSION = "debt_classification_v1"


class CorpusKind(str, Enum):
    ENGINEERING = "engineering"
    REAL_WORLD = "real_world"


class BehaviorFamilyId(str, Enum):
    FILESYSTEM = "filesystem"
    CONSOLE = "console"
    MEMORY = "memory"
    CRT = "crt"
    REGISTRY = "registry"
    NETWORKING = "networking"
    SYNCHRONIZATION = "synchronization"
    GUI = "gui"


class CorpusProvenance(BaseModel):
    source: str
    fixture_path: str = ""


class CorpusEnrollmentEntry(BaseModel):
    entry_id: str
    application_fingerprint: str
    binary_digest: str
    provenance: CorpusProvenance
    enrolled_at: str

    def to_canonical_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "application_fingerprint": self.application_fingerprint,
            "binary_digest": self.binary_digest,
            "provenance": self.provenance.model_dump(mode="json"),
            "enrolled_at": self.enrolled_at,
        }


class CorpusManifest(BaseModel):
    schema_version: str
    corpus: CorpusKind
    entries: List[CorpusEnrollmentEntry] = Field(default_factory=list)
    digest: str

    @field_validator("schema_version")
    @classmethod
    def _require_schema_version(cls, value: str) -> str:
        if value != RUNTIME_INTELLIGENCE_SCHEMA_VERSION:
            raise ValueError(f"unsupported corpus schema: {value}")
        return value

    @field_validator("entries")
    @classmethod
    def _sort_entries(
        cls,
        value: List[CorpusEnrollmentEntry],
    ) -> List[CorpusEnrollmentEntry]:
        return sorted(value, key=lambda entry: entry.entry_id)


class CanonicalFamily(BaseModel):
    family_id: BehaviorFamilyId
    name: str
    description: str


class BehaviorFamilyMapping(BaseModel):
    behavior_id: str
    family_id: BehaviorFamilyId


def compute_manifest_digest(entries: List[CorpusEnrollmentEntry]) -> str:
    """Deterministic digest over canonical serialized enrollment entries."""
    payload: Mapping[str, Any] = {
        "entries": [entry.to_canonical_dict() for entry in sorted(entries, key=lambda e: e.entry_id)],
    }
    return sha256_v1(payload)


def compute_enrollment_entry_id(*, corpus: CorpusKind, binary_digest: str) -> str:
    return sha256_v1({"corpus": corpus.value, "binary_digest": binary_digest})


def compute_application_fingerprint(
    *,
    binary_digest: str,
    fixture_name: str,
    corpus: CorpusKind,
) -> str:
    return sha256_v1(
        {
            "binary_digest": binary_digest,
            "fixture_name": fixture_name,
            "corpus_track": corpus.value,
        }
    )


class CompatibilityIndexStatus(str, Enum):
    COMPUTED = "computed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class EvidenceRatio(BaseModel):
    numerator: int = Field(ge=0, default=0)
    denominator: int = Field(ge=0, default=0)
    value: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    available: bool = True
    insufficient_reason: Optional[str] = None
    evidence_references: List[str] = Field(default_factory=list)
    snapshot_digest: Optional[str] = None

    @model_validator(mode="after")
    def _validate_ratio(self) -> "EvidenceRatio":
        if self.denominator > 0 and self.numerator > self.denominator:
            raise ValueError("numerator cannot exceed denominator when denominator is positive")
        return self


class CompatibilityIndexComponent(BaseModel):
    component_id: str
    raw_weight: float
    effective_weight: float
    value: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    available: bool
    sample_size: SampleSize
    limitations: List[str] = Field(default_factory=list)
    evidence_references: List[str] = Field(default_factory=list)
    insufficient_reason: Optional[str] = None
    snapshot_digest: Optional[str] = None


class CompatibilityIndexInput(BaseModel):
    corpus: CorpusKind
    family_id: BehaviorFamilyId
    provider_id: str
    behavior_coverage: EvidenceRatio
    authoritative_verification_rate: EvidenceRatio
    calibration_accuracy: EvidenceRatio
    governance_maturity: EvidenceRatio
    certification_level: EvidenceRatio
    registry_version: Optional[str] = None
    provider_version: Optional[str] = None
    evidence_snapshot_digest: str
    generated_from: str = ""
    limitations: List[str] = Field(default_factory=list)


class CompatibilityIndexReport(BaseModel):
    corpus: CorpusKind
    family_id: BehaviorFamilyId
    provider_id: str
    index_value: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    status: CompatibilityIndexStatus
    components: List[CompatibilityIndexComponent]
    formula_version: str
    schema_version: str
    limitations: List[str] = Field(default_factory=list)
    evidence_references: List[str] = Field(default_factory=list)
    report_digest: str
    registry_version: Optional[str] = None
    provider_version: Optional[str] = None
    evidence_snapshot_digest: str
    generated_from: str = ""
    generated_at: Optional[str] = None


class KnowledgeCoverageStatus(str, Enum):
    COMPUTED = "computed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class KnowledgeCoverageComponent(BaseModel):
    component_id: str
    numerator: int = Field(ge=0, default=0)
    denominator: int = Field(ge=0, default=0)
    value: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    available: bool
    raw_weight: float
    effective_weight: float
    insufficient_reason: Optional[str] = None
    limitations: List[str] = Field(default_factory=list)
    evidence_references: List[str] = Field(default_factory=list)
    snapshot_digest: Optional[str] = None


class CompatibilityKnowledgeInput(BaseModel):
    corpus: CorpusKind
    family_id: BehaviorFamilyId
    provider_id: Optional[str] = None
    behavior_classification_coverage: EvidenceRatio
    blocker_explanation_coverage: EvidenceRatio
    failure_attribution_coverage: EvidenceRatio
    prediction_outcome_linkage_coverage: EvidenceRatio
    limitation_documentation_coverage: EvidenceRatio
    contradiction_quality: EvidenceRatio
    observed_behavior_count: int = Field(ge=0, default=0)
    classified_behavior_count: int = Field(ge=0, default=0)
    explained_blocker_count: int = Field(ge=0, default=0)
    unknown_behavior_ids: List[str] = Field(default_factory=list)
    unknown_api_names: List[str] = Field(default_factory=list)
    attributed_failure_count: int = Field(ge=0, default=0)
    unattributed_failure_count: int = Field(ge=0, default=0)
    contradictory_evidence_count: int = Field(ge=0, default=0)
    evidence_backed_limitations: List[str] = Field(default_factory=list)
    evidence_snapshot_digest: str
    registry_version: Optional[str] = None
    provider_version: Optional[str] = None
    evidence_references: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)


class CompatibilityKnowledgeCoverageReport(BaseModel):
    corpus: CorpusKind
    family_id: BehaviorFamilyId
    provider_id: Optional[str] = None
    status: KnowledgeCoverageStatus
    knowledge_coverage_value: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    components: List[KnowledgeCoverageComponent]
    observed_behavior_count: int = Field(ge=0, default=0)
    classified_behavior_count: int = Field(ge=0, default=0)
    explained_blocker_count: int = Field(ge=0, default=0)
    unknown_behavior_ids: List[str] = Field(default_factory=list)
    unknown_api_names: List[str] = Field(default_factory=list)
    attributed_failure_count: int = Field(ge=0, default=0)
    unattributed_failure_count: int = Field(ge=0, default=0)
    contradictory_evidence_count: int = Field(ge=0, default=0)
    evidence_backed_limitations: List[str] = Field(default_factory=list)
    formula_version: str
    schema_version: str
    limitations: List[str] = Field(default_factory=list)
    evidence_references: List[str] = Field(default_factory=list)
    report_digest: str
    registry_version: Optional[str] = None
    provider_version: Optional[str] = None
    evidence_snapshot_digest: str
    generated_at: Optional[str] = None


class CompatibilityDebtKind(str, Enum):
    UNSUPPORTED_BEHAVIOR = "unsupported_behavior"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    UNKNOWN_API = "unknown_api"
    UNKNOWN_BEHAVIOR = "unknown_behavior"
    BLOCKED_BY_PREREQUISITE = "blocked_by_prerequisite"
    CALIBRATION_FALSE_POSITIVE = "calibration_false_positive"
    CALIBRATION_FALSE_NEGATIVE = "calibration_false_negative"
    STALE_EVIDENCE = "stale_evidence"
    STALE_CERTIFICATION = "stale_certification"
    MATURITY_REGRESSION = "maturity_regression"
    MISSING_FIXTURE = "missing_fixture"
    ACKNOWLEDGED_OUT_OF_SCOPE = "acknowledged_out_of_scope"


class CompatibilityDebtDisposition(str, Enum):
    ADDRESSABLE = "addressable"
    BLOCKED_BY_PREREQUISITE = "blocked_by_prerequisite"
    ACKNOWLEDGED_OUT_OF_SCOPE = "acknowledged_out_of_scope"
    UNKNOWN = "unknown"
    STALE_EVIDENCE = "stale_evidence"


class CompatibilityDebtSignal(BaseModel):
    kind: CompatibilityDebtKind
    corpus: CorpusKind
    family_id: BehaviorFamilyId
    capability_id: str
    evidence_snapshot_digest: str
    evidence_references: List[str] = Field(default_factory=list)
    provider_id: Optional[str] = None
    behavior_id: Optional[str] = None
    distinct_binary_count: int = Field(ge=0, default=0)
    distinct_application_count: int = Field(ge=0, default=0)
    blocked_session_count: int = Field(ge=0, default=0)
    calibration_gap_count: int = Field(ge=0, default=0)
    authoritative_failure_count: int = Field(ge=0, default=0)
    security_risk_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    semantic_risk_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    first_observed: Optional[str] = None
    last_observed: Optional[str] = None
    limitations: List[str] = Field(default_factory=list)
    prerequisite_capability_ids: List[str] = Field(default_factory=list)
    prerequisites_unmet: bool = False
    fixture_available: bool = False
    current_maturity: Optional[str] = None
    current_certification: Optional[str] = None
    evidence_stale: bool = False
    explicitly_out_of_scope: bool = False
    stderr_only: bool = False
    affected_binary_digests: List[str] = Field(default_factory=list)
    affected_application_fingerprints: List[str] = Field(default_factory=list)
    expansion_candidate_id: Optional[str] = None
    work_item_id: Optional[str] = None
    certification_artifact_id: Optional[str] = None
    governance_artifact_id: Optional[str] = None


class CompatibilityDebtItem(BaseModel):
    debt_id: str
    kind: CompatibilityDebtKind
    disposition: CompatibilityDebtDisposition
    severity: str
    corpus: CorpusKind
    family_id: BehaviorFamilyId
    capability_id: str
    evidence_snapshot_digest: str
    evidence_references: List[str] = Field(default_factory=list)
    provider_id: Optional[str] = None
    behavior_id: Optional[str] = None
    distinct_binary_count: int = Field(ge=0, default=0)
    distinct_application_count: int = Field(ge=0, default=0)
    blocked_session_count: int = Field(ge=0, default=0)
    calibration_gap_count: int = Field(ge=0, default=0)
    first_observed: Optional[str] = None
    last_observed: Optional[str] = None
    age_days: Optional[int] = Field(default=None, ge=0)
    prerequisite_capability_ids: List[str] = Field(default_factory=list)
    fixture_available: bool = False
    current_maturity: Optional[str] = None
    current_certification: Optional[str] = None
    severity_factors: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    expansion_candidate_id: Optional[str] = None
    work_item_id: Optional[str] = None
    schema_version: str
    formula_version: str
    digest: str


class CompatibilityDebtReport(BaseModel):
    corpus: CorpusKind
    family_id: BehaviorFamilyId
    items: List[CompatibilityDebtItem]
    evidence_snapshot_digest: str
    report_digest: str
    schema_version: str
    formula_version: str
    provider_id: Optional[str] = None
    counts_by_kind: Dict[str, int] = Field(default_factory=dict)
    counts_by_disposition: Dict[str, int] = Field(default_factory=dict)
    counts_by_severity: Dict[str, int] = Field(default_factory=dict)
    total_distinct_binaries: int = Field(ge=0, default=0)
    total_distinct_applications: int = Field(ge=0, default=0)
    summed_item_application_mentions: int = Field(ge=0, default=0)
    limitations: List[str] = Field(default_factory=list)
    evidence_references: List[str] = Field(default_factory=list)
    generated_at: Optional[str] = None
