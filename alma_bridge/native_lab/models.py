"""Native Runtime Development Laboratory models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

NATIVE_LAB_SCHEMA_VERSION = "native_lab_v1"
NATIVE_LAB_ENGINE_VERSION = "native_lab_service_v1"
NATIVE_LAB_PROVIDER_ID = "native_alma"
NATIVE_LAB_IMPLEMENTATION_VERSION = "0.2.1-m2"

SEEDED_WORK_ITEM_ID = "wi_native_alma_filesystem_basic_io_append_existing_file_v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class WorkItemStatus(str, Enum):
    PROPOSED = "proposed"
    TRIAGED = "triaged"
    ACCEPTED = "accepted"
    IN_DESIGN = "in_design"
    IMPLEMENTATION_IN_PROGRESS = "implementation_in_progress"
    IMPLEMENTATION_COMPLETE = "implementation_complete"
    TESTING = "testing"
    VERIFICATION_PENDING = "verification_pending"
    CERTIFICATION_PENDING = "certification_pending"
    GOVERNANCE_PENDING = "governance_pending"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class ChecklistCategory(str, Enum):
    DESIGN = "design"
    IMPLEMENTATION = "implementation"
    TESTING = "testing"
    CONFORMANCE = "conformance"
    PERFORMANCE = "performance"
    VERIFICATION = "verification"
    CERTIFICATION = "certification"
    GOVERNANCE = "governance"


class ChecklistItemStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SATISFIED = "satisfied"
    NOT_APPLICABLE = "not_applicable"
    FAILED = "failed"


class AcceptanceCriterionStatus(str, Enum):
    PENDING = "pending"
    SATISFIED = "satisfied"
    FAILED = "failed"
    WAIVED = "waived"


class RiskSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskCategory(str, Enum):
    SECURITY = "security"
    SEMANTIC = "semantic"


class EvidenceLinkKind(str, Enum):
    FIXTURE = "fixture"
    CALIBRATION = "calibration"
    ANALYSIS = "analysis"
    EXPANSION = "expansion"
    CERTIFICATION = "certification"
    BENCHMARK = "benchmark"
    BEHAVIOR_TEST = "behavior_test"
    VERIFICATION = "verification"
    SPECIFICATION = "specification"


class PriorityDimensionsSnapshot(BaseModel):
    demand_score: float = 0.0
    bounded_impact_score: float = 0.0
    engineering_cost_score: float = 0.0
    security_risk_score: float = 0.0
    semantic_risk_score: float = 0.0
    evidence_quality_score: float = 0.0
    testability_score: float = 0.0
    composite_score: float = 0.0


class ObservedDemandSnapshot(BaseModel):
    distinct_binary_digests: int = 0
    distinct_application_fingerprints: int = 0
    blocked_session_count: int = 0
    false_positive_gap_count: int = 0
    most_recent_evidence_at: Optional[str] = None


class BoundedImpactSnapshot(BaseModel):
    analyses_blocker_removable: int = 0
    binaries_ineligible_to_eligible: int = 0
    behavior_coverage_increase_percent: float = 0.0
    impact_summary: str = ""


class EngineeringAcceptanceCriterion(BaseModel):
    criterion_id: str
    description: str
    category: ChecklistCategory
    status: AcceptanceCriterionStatus = AcceptanceCriterionStatus.PENDING
    critical: bool = False
    security_related: bool = False
    verification_related: bool = False
    waiver_reviewer: Optional[str] = None
    waiver_reason: Optional[str] = None
    waiver_expires_at: Optional[str] = None
    evidence_reference_ids: List[str] = Field(default_factory=list)
    updated_at: str = Field(default_factory=utc_now_iso)


class ChecklistItem(BaseModel):
    item_id: str
    category: ChecklistCategory
    ordinal: int
    title: str
    description: str = ""
    status: ChecklistItemStatus = ChecklistItemStatus.PENDING
    required: bool = True
    evidence_reference_ids: List[str] = Field(default_factory=list)


class EvidenceReference(BaseModel):
    reference_id: str
    kind: EvidenceLinkKind
    source: str
    artifact_id: str
    digest: str = ""
    fixture_path: Optional[str] = None
    attached_at: str = Field(default_factory=utc_now_iso)
    attached_by: str = ""
    evidence_stale: bool = False
    stale_reason: str = ""


class SecurityReviewItem(BaseModel):
    item_id: str
    category: str
    description: str
    severity: RiskSeverity = RiskSeverity.MEDIUM
    addressed: bool = False


class StatusEvent(BaseModel):
    event_id: str
    work_item_id: str
    from_status: Optional[WorkItemStatus] = None
    to_status: WorkItemStatus
    actor: str = ""
    rationale: str = ""
    recorded_at: str = Field(default_factory=utc_now_iso)
    event_digest: str = ""


class RiskReviewRecord(BaseModel):
    review_id: str
    work_item_id: str
    category: RiskCategory
    severity: RiskSeverity
    likelihood: str = "medium"
    description: str
    mitigation: str = ""
    residual_risk: str = ""
    evidence_reference_ids: List[str] = Field(default_factory=list)
    reviewer: str = ""
    recorded_at: str = Field(default_factory=utc_now_iso)
    review_digest: str = ""


class DependencyEdge(BaseModel):
    predecessor_id: str
    successor_id: str
    relationship: str = "prerequisite"
    description: str = ""


class NativeRuntimeEngineeringWorkItem(BaseModel):
    work_item_id: str
    title: str
    provider_id: str = NATIVE_LAB_PROVIDER_ID
    capability_id: str
    behavior_id: str
    bounded_scope: str
    architecture: str = "x64"
    subsystem: str = "filesystem"
    source_expansion_candidate_id: str = ""
    priority_dimensions: PriorityDimensionsSnapshot = Field(
        default_factory=PriorityDimensionsSnapshot
    )
    observed_demand: ObservedDemandSnapshot = Field(default_factory=ObservedDemandSnapshot)
    estimated_bounded_impact: BoundedImpactSnapshot = Field(
        default_factory=BoundedImpactSnapshot
    )
    acceptance_criteria: List[EngineeringAcceptanceCriterion] = Field(default_factory=list)
    required_fixtures: List[str] = Field(default_factory=list)
    required_tests: List[str] = Field(default_factory=list)
    required_benchmarks: List[str] = Field(default_factory=list)
    security_review_items: List[SecurityReviewItem] = Field(default_factory=list)
    prerequisite_work_item_ids: List[str] = Field(default_factory=list)
    status: WorkItemStatus = WorkItemStatus.PROPOSED
    owner: str = ""
    reviewer: str = ""
    evidence_references: List[EvidenceReference] = Field(default_factory=list)
    evidence_stale: bool = False
    expansion_plan_version: str = ""
    registry_version: str = ""
    provider_version_scope: str = ""
    work_item_digest: str = ""
    superseded_by: Optional[str] = None
    supersedes: Optional[str] = None
    schema_version: str = NATIVE_LAB_SCHEMA_VERSION
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class EngineeringCard(BaseModel):
    work_item_id: str
    title: str
    bounded_scope: str
    provider_id: str
    capability_id: str
    behavior_id: str
    status: WorkItemStatus
    demand_summary: str
    impact_summary: str
    current_maturity: str = ""
    current_certification_level: str = ""
    prerequisites: List[str] = Field(default_factory=list)
    required_evidence: List[str] = Field(default_factory=list)
    security_review_items: List[SecurityReviewItem] = Field(default_factory=list)
    checklist_progress: Dict[str, int] = Field(default_factory=dict)
    blockers: List[str] = Field(default_factory=list)
    evidence_stale: bool = False
    owner: str = ""
    reviewer: str = ""


class ChecklistEvaluation(BaseModel):
    work_item_id: str
    items: List[ChecklistItem] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)
    progress_pct: float = 0.0
    evaluation_digest: str = ""


class DependencyGraph(BaseModel):
    work_item_id: str
    edges: List[DependencyEdge] = Field(default_factory=list)
    blocked_by: List[str] = Field(default_factory=list)
    blocks: List[str] = Field(default_factory=list)
    critical_path: List[str] = Field(default_factory=list)
    has_cycle: bool = False
    graph_digest: str = ""


class WorkItemHistory(BaseModel):
    work_item_id: str
    events: List[StatusEvent] = Field(default_factory=list)
    history_digest: str = ""


class NativeLabDashboard(BaseModel):
    generated_at: str = Field(default_factory=utc_now_iso)
    schema_version: str = NATIVE_LAB_SCHEMA_VERSION
    total_work_items: int = 0
    by_status: Dict[str, int] = Field(default_factory=dict)
    backlog_count: int = 0
    active_count: int = 0
    verification_queue_count: int = 0
    certification_queue_count: int = 0
    completed_count: int = 0
    blocked_count: int = 0
    stale_evidence_count: int = 0
    sample_sizes: Dict[str, int] = Field(default_factory=dict)
    limitations: List[str] = Field(default_factory=list)
