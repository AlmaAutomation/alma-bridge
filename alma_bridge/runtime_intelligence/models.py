"""Domain models for Runtime Intelligence."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.research.models import SampleSize

RUNTIME_INTELLIGENCE_SCHEMA_VERSION = "runtime_intelligence_corpus_v1"
RUNTIME_INTELLIGENCE_INDEX_SCHEMA_VERSION = "runtime_intelligence_index_v1"
RUNTIME_INTELLIGENCE_KNOWLEDGE_SCHEMA_VERSION = "runtime_intelligence_knowledge_v1"
RUNTIME_INTELLIGENCE_DEBT_SCHEMA_VERSION = "runtime_intelligence_debt_v1"
RUNTIME_INTELLIGENCE_HYPOTHESIS_SCHEMA_VERSION = "runtime_intelligence_hypothesis_v1"
COMPATIBILITY_INDEX_FORMULA_VERSION = "compatibility_index_v1"
KNOWLEDGE_COVERAGE_FORMULA_VERSION = "knowledge_coverage_v1"
DEBT_CLASSIFICATION_FORMULA_VERSION = "debt_classification_v1"
HYPOTHESIS_FORMULA_VERSION = "engineering_hypothesis_v1"


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


class EngineeringHypothesisResult(str, Enum):
    CONFIRMED = "confirmed"
    PARTIALLY_CONFIRMED = "partially_confirmed"
    CONTRADICTED = "contradicted"
    INDETERMINATE = "indeterminate"


class EngineeringHypothesisSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    hypothesis_id: str
    created_at: str
    corpus: CorpusKind
    provider_id: str
    provider_version_scope: str
    family_id: BehaviorFamilyId
    capability_id: str
    bounded_scope: str
    evidence_snapshot_digest: str
    snapshot_digest: str
    schema_version: str
    formula_version: str
    behavior_id: Optional[str] = None
    predicted_application_fingerprints: tuple[str, ...] = ()
    predicted_binary_digests: tuple[str, ...] = ()
    predicted_application_classes: tuple[str, ...] = ()
    predicted_applications_unblocked_count: int = Field(ge=0, default=0)
    predicted_application_classes_unblocked_count: int = Field(ge=0, default=0)
    predicted_confidence: str = "unknown"
    predicted_limitations: tuple[str, ...] = ()
    source_expansion_candidate_ids: tuple[str, ...] = ()
    source_debt_item_ids: tuple[str, ...] = ()
    source_registry_version: str = ""
    source_expansion_plan_version: str = ""
    evidence_references: tuple[str, ...] = ()


class EngineeringHypothesisOutcomeLink(BaseModel):
    model_config = ConfigDict(frozen=True)

    outcome_link_id: str
    hypothesis_id: str
    linked_at: str
    evidence_snapshot_digest: str
    link_digest: str
    schema_version: str
    implementation_work_item_id: Optional[str] = None
    implementation_version: Optional[str] = None
    provider_version: Optional[str] = None
    observed_application_fingerprints: tuple[str, ...] = ()
    observed_binary_digests: tuple[str, ...] = ()
    observed_application_classes: tuple[str, ...] = ()
    observed_verified_successes: int = Field(ge=0, default=0)
    observed_verified_failures: int = Field(ge=0, default=0)
    observed_unverifiable: int = Field(ge=0, default=0)
    observed_blockers_removed: tuple[str, ...] = ()
    observed_new_blockers: tuple[str, ...] = ()
    authoritative_outcome_references: tuple[str, ...] = ()
    calibration_record_ids: tuple[str, ...] = ()
    certification_artifact_ids: tuple[str, ...] = ()
    governance_artifact_ids: tuple[str, ...] = ()
    evidence_references: tuple[str, ...] = ()
    stderr_only_failure: bool = False


class EngineeringHypothesisEvaluation(BaseModel):
    hypothesis_id: str
    corpus: CorpusKind
    family_id: BehaviorFamilyId
    capability_id: str
    result: EngineeringHypothesisResult
    evaluation_digest: str
    predicted_applications_unblocked_count: int = Field(ge=0, default=0)
    observed_applications_unblocked_count: int = Field(ge=0, default=0)
    predicted_application_classes_unblocked_count: int = Field(ge=0, default=0)
    observed_application_classes_unblocked_count: int = Field(ge=0, default=0)
    application_variance: int = 0
    application_class_variance: int = 0
    observed_verified_successes: int = Field(ge=0, default=0)
    observed_verified_failures: int = Field(ge=0, default=0)
    confidence: str = "unknown"
    confidence_factors: List[str] = Field(default_factory=list)
    behavior_id: Optional[str] = None
    limitations: List[str] = Field(default_factory=list)
    evidence_references: List[str] = Field(default_factory=list)
    outcome_link_digests: List[str] = Field(default_factory=list)
    snapshot_digest: str = ""


RUNTIME_INTELLIGENCE_SERVICE_SCHEMA_VERSION = "runtime_intelligence_service_v1"
RUNTIME_INTELLIGENCE_ENGINE_VERSION = "runtime_intelligence_service_v1"
RUNTIME_INTELLIGENCE_HISTORY_SCHEMA_VERSION = "runtime_intelligence_history_v1"


class RuntimeIntelligenceHistoryStatus(str, Enum):
    COMPUTED = "computed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class RuntimeIntelligenceMetricId(str, Enum):
    COMPATIBILITY_INDEX = "compatibility_index"
    KNOWLEDGE_COVERAGE = "knowledge_coverage"
    COMPATIBILITY_DEBT = "compatibility_debt"
    HYPOTHESIS_ACCURACY = "hypothesis_accuracy"
    VERIFICATION_RATE = "verification_rate"
    PREDICTION_ACCURACY = "prediction_accuracy"
    DETERMINISM_RATE = "determinism_rate"
    APPLICATIONS_UNLOCKED = "applications_unlocked"
    APPLICATION_CLASSES_UNLOCKED = "application_classes_unlocked"


class RuntimeIntelligenceError(Exception):
    """Base error for Runtime Intelligence service boundaries."""


class CorpusRequiredError(RuntimeIntelligenceError):
    """Raised when an explicit corpus query parameter is missing."""


class InvalidCorpusError(RuntimeIntelligenceError):
    """Raised when corpus value is not engineering or real_world."""


class InvalidFamilyError(RuntimeIntelligenceError):
    """Raised when family_id is not one of the eight canonical families."""


class InvalidProviderError(RuntimeIntelligenceError):
    """Raised when provider_id cannot be resolved in the requested scope."""


class HypothesisNotFoundError(RuntimeIntelligenceError):
    """Raised when hypothesis_id is unknown in the requested corpus scope."""


class HypothesisTimelineConflictError(RuntimeIntelligenceError):
    """Raised when an immutable hypothesis timeline event conflicts with prior payload."""


class EvidenceSnapshotMismatchError(RuntimeIntelligenceError):
    """Raised when evidence snapshot digest does not match prepared inputs."""


class QueryMetadata(BaseModel):
    excluded_unenrolled_artifact_count: int = Field(ge=0, default=0)
    limitations: List[str] = Field(default_factory=list)


class RuntimeIntelligenceHistoryPoint(BaseModel):
    timestamp_bucket: str
    corpus: CorpusKind
    family_id: Optional[BehaviorFamilyId] = None
    provider_id: Optional[str] = None
    metric_id: str
    numerator: int = Field(ge=0, default=0)
    denominator: int = Field(ge=0, default=0)
    sample_size: SampleSize
    value: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    evidence_references: List[str] = Field(default_factory=list)
    status: RuntimeIntelligenceHistoryStatus


class RuntimeIntelligenceHistoryReport(BaseModel):
    corpus: CorpusKind
    metric_id: str
    family_id: Optional[BehaviorFamilyId] = None
    provider_id: Optional[str] = None
    points: List[RuntimeIntelligenceHistoryPoint] = Field(default_factory=list)
    report_digest: str
    limitations: List[str] = Field(default_factory=list)
    schema_version: str = RUNTIME_INTELLIGENCE_HISTORY_SCHEMA_VERSION


class RuntimeIntelligenceFamilySummary(BaseModel):
    family_id: BehaviorFamilyId
    name: str
    description: str
    enrolled_application_count: int = Field(ge=0, default=0)


class RuntimeIntelligenceHypothesisSummary(BaseModel):
    total_count: int = Field(ge=0, default=0)
    by_result: Dict[str, int] = Field(default_factory=dict)
    limitations: List[str] = Field(default_factory=list)


class TimelineAppendStatus(str, Enum):
    APPENDED = "appended"
    DUPLICATE = "duplicate"


class TimelineAppendResult(BaseModel):
    status: TimelineAppendStatus
    event_id: str
    bundle_id: str = ""


class RuntimeIntelligenceReport(BaseModel):
    corpus: CorpusKind
    generated_at: str
    evidence_snapshot_digest: str
    family_summaries: List[RuntimeIntelligenceFamilySummary] = Field(default_factory=list)
    compatibility_indexes: List[CompatibilityIndexReport] = Field(default_factory=list)
    knowledge_coverage: List[CompatibilityKnowledgeCoverageReport] = Field(default_factory=list)
    debt_reports: List[CompatibilityDebtReport] = Field(default_factory=list)
    hypothesis_summary: RuntimeIntelligenceHypothesisSummary = Field(
        default_factory=RuntimeIntelligenceHypothesisSummary
    )
    history_summary: Optional[Dict[str, Any]] = None
    excluded_unenrolled_artifact_count: int = Field(ge=0, default=0)
    limitations: List[str] = Field(default_factory=list)
    evidence_references: List[str] = Field(default_factory=list)
    schema_version: str = RUNTIME_INTELLIGENCE_SERVICE_SCHEMA_VERSION
    engine_version: str = RUNTIME_INTELLIGENCE_ENGINE_VERSION
    report_digest: str = ""


def compute_runtime_intelligence_report_digest(
    *,
    corpus: CorpusKind,
    evidence_snapshot_digest: str,
    family_summaries: List[RuntimeIntelligenceFamilySummary],
    compatibility_indexes: List[CompatibilityIndexReport],
    knowledge_coverage: List[CompatibilityKnowledgeCoverageReport],
    debt_reports: List[CompatibilityDebtReport],
    hypothesis_summary: RuntimeIntelligenceHypothesisSummary,
    excluded_unenrolled_artifact_count: int,
    limitations: List[str],
    evidence_references: List[str],
) -> str:
    payload: Mapping[str, Any] = {
        "corpus": corpus.value,
        "evidence_snapshot_digest": evidence_snapshot_digest,
        "family_summaries": [
            {
                "family_id": summary.family_id.value,
                "enrolled_application_count": summary.enrolled_application_count,
            }
            for summary in sorted(family_summaries, key=lambda s: s.family_id.value)
        ],
        "compatibility_indexes": sorted(r.report_digest for r in compatibility_indexes),
        "knowledge_coverage": sorted(r.report_digest for r in knowledge_coverage),
        "debt_reports": sorted(r.report_digest for r in debt_reports),
        "hypothesis_summary": {
            "total_count": hypothesis_summary.total_count,
            "by_result": dict(sorted(hypothesis_summary.by_result.items())),
        },
        "excluded_unenrolled_artifact_count": excluded_unenrolled_artifact_count,
        "limitations": sorted(set(limitations)),
        "evidence_references": sorted(set(evidence_references)),
        "schema_version": RUNTIME_INTELLIGENCE_SERVICE_SCHEMA_VERSION,
        "engine_version": RUNTIME_INTELLIGENCE_ENGINE_VERSION,
    }
    return sha256_v1(payload)


def compute_history_report_digest(
    *,
    corpus: CorpusKind,
    metric_id: str,
    family_id: Optional[BehaviorFamilyId],
    provider_id: Optional[str],
    points: List[RuntimeIntelligenceHistoryPoint],
) -> str:
    payload: Mapping[str, Any] = {
        "corpus": corpus.value,
        "metric_id": metric_id,
        "family_id": family_id.value if family_id else "",
        "provider_id": provider_id or "",
        "points": [
            {
                "timestamp_bucket": point.timestamp_bucket,
                "metric_id": point.metric_id,
                "numerator": point.numerator,
                "denominator": point.denominator,
                "value": point.value,
                "status": point.status.value,
            }
            for point in sorted(points, key=lambda p: (p.timestamp_bucket, p.metric_id))
        ],
        "schema_version": RUNTIME_INTELLIGENCE_HISTORY_SCHEMA_VERSION,
    }
    return sha256_v1(payload)


class EngineeringHypothesisResult(str, Enum):
    CONFIRMED = "confirmed"
    PARTIALLY_CONFIRMED = "partially_confirmed"
    CONTRADICTED = "contradicted"
    INDETERMINATE = "indeterminate"


class EngineeringHypothesisSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    hypothesis_id: str
    created_at: str
    corpus: CorpusKind
    provider_id: str
    provider_version_scope: str
    family_id: BehaviorFamilyId
    capability_id: str
    bounded_scope: str
    evidence_snapshot_digest: str
    snapshot_digest: str
    schema_version: str
    formula_version: str
    behavior_id: Optional[str] = None
    predicted_application_fingerprints: tuple[str, ...] = ()
    predicted_binary_digests: tuple[str, ...] = ()
    predicted_application_classes: tuple[str, ...] = ()
    predicted_applications_unblocked_count: int = Field(ge=0, default=0)
    predicted_application_classes_unblocked_count: int = Field(ge=0, default=0)
    predicted_confidence: str = "unknown"
    predicted_limitations: tuple[str, ...] = ()
    source_expansion_candidate_ids: tuple[str, ...] = ()
    source_debt_item_ids: tuple[str, ...] = ()
    source_registry_version: str = ""
    source_expansion_plan_version: str = ""
    evidence_references: tuple[str, ...] = ()


class EngineeringHypothesisOutcomeLink(BaseModel):
    model_config = ConfigDict(frozen=True)

    outcome_link_id: str
    hypothesis_id: str
    linked_at: str
    evidence_snapshot_digest: str
    link_digest: str
    schema_version: str
    implementation_work_item_id: Optional[str] = None
    implementation_version: Optional[str] = None
    provider_version: Optional[str] = None
    observed_application_fingerprints: tuple[str, ...] = ()
    observed_binary_digests: tuple[str, ...] = ()
    observed_application_classes: tuple[str, ...] = ()
    observed_verified_successes: int = Field(ge=0, default=0)
    observed_verified_failures: int = Field(ge=0, default=0)
    observed_unverifiable: int = Field(ge=0, default=0)
    observed_blockers_removed: tuple[str, ...] = ()
    observed_new_blockers: tuple[str, ...] = ()
    authoritative_outcome_references: tuple[str, ...] = ()
    calibration_record_ids: tuple[str, ...] = ()
    certification_artifact_ids: tuple[str, ...] = ()
    governance_artifact_ids: tuple[str, ...] = ()
    evidence_references: tuple[str, ...] = ()
    stderr_only_failure: bool = False


class EngineeringHypothesisEvaluation(BaseModel):
    hypothesis_id: str
    corpus: CorpusKind
    family_id: BehaviorFamilyId
    capability_id: str
    result: EngineeringHypothesisResult
    evaluation_digest: str
    predicted_applications_unblocked_count: int = Field(ge=0, default=0)
    observed_applications_unblocked_count: int = Field(ge=0, default=0)
    predicted_application_classes_unblocked_count: int = Field(ge=0, default=0)
    observed_application_classes_unblocked_count: int = Field(ge=0, default=0)
    application_variance: int = 0
    application_class_variance: int = 0
    observed_verified_successes: int = Field(ge=0, default=0)
    observed_verified_failures: int = Field(ge=0, default=0)
    confidence: str = "unknown"
    confidence_factors: List[str] = Field(default_factory=list)
    behavior_id: Optional[str] = None
    limitations: List[str] = Field(default_factory=list)
    evidence_references: List[str] = Field(default_factory=list)
    outcome_link_digests: List[str] = Field(default_factory=list)
    snapshot_digest: str = ""
