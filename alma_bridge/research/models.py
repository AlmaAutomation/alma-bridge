"""Research report models — deterministic, sample-sized, limitation-aware."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

RESEARCH_SCHEMA_VERSION = "alma_research_v1"
RESEARCH_ENGINE_VERSION = "alma_research_service_v1"

CAUSATION_FORBIDDEN = frozenset(
    {"causes", "caused by", "because of", "leads to", "results in"}
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ResearchReportType(str, Enum):
    TOP_UNSUPPORTED_BEHAVIORS = "top_unsupported_behaviors"
    TOP_CALIBRATION_GAPS = "top_calibration_gaps"
    UNKNOWN_APIS = "most_observed_unknown_apis"
    CAPABILITY_MATURITY_GROWTH = "capability_maturity_growth"
    PREDICTION_ACCURACY_OVER_TIME = "prediction_accuracy_over_time"
    BEHAVIOR_COVERAGE_EVOLUTION = "behavior_coverage_evolution"
    NATIVE_RUNTIME_GROWTH = "native_runtime_growth"
    GOVERNANCE_VELOCITY = "governance_velocity"
    EXPANSION_BACKLOG = "expansion_backlog"
    VERIFICATION_TRENDS = "verification_trends"


REPORT_TYPE_LABELS: Dict[ResearchReportType, str] = {
    ResearchReportType.TOP_UNSUPPORTED_BEHAVIORS: "Top Unsupported Behaviors",
    ResearchReportType.TOP_CALIBRATION_GAPS: "Top Calibration Gaps",
    ResearchReportType.UNKNOWN_APIS: "Most Frequently Observed Unknown APIs",
    ResearchReportType.CAPABILITY_MATURITY_GROWTH: "Capability Maturity Growth",
    ResearchReportType.PREDICTION_ACCURACY_OVER_TIME: "Prediction Accuracy Over Time",
    ResearchReportType.BEHAVIOR_COVERAGE_EVOLUTION: "Behavior Coverage Evolution",
    ResearchReportType.NATIVE_RUNTIME_GROWTH: "Native Runtime Growth",
    ResearchReportType.GOVERNANCE_VELOCITY: "Governance Velocity",
    ResearchReportType.EXPANSION_BACKLOG: "Expansion Plan Completion / Backlog",
    ResearchReportType.VERIFICATION_TRENDS: "Verification Trends",
}


class SampleSize(BaseModel):
    numerator: int = Field(ge=0, default=0)
    denominator: int = Field(ge=0, default=0)
    label: str = ""


class TimeWindow(BaseModel):
    start: Optional[str] = None
    end: Optional[str] = None
    label: str = "all_time"


class ReportConfidence(BaseModel):
    score: float = Field(ge=0.0, le=1.0, default=0.0)
    basis: str = ""
    factors: List[str] = Field(default_factory=list)


class EvidenceReference(BaseModel):
    source: str
    artifact_id: str
    digest: str = ""


class ReportMetadata(BaseModel):
    report_type: ResearchReportType
    report_digest: str
    generated_at: str
    schema_version: str = RESEARCH_SCHEMA_VERSION
    engine_version: str = RESEARCH_ENGINE_VERSION
    sample_size: SampleSize
    time_window: TimeWindow
    registry_version: str = ""
    provider_versions: Dict[str, str] = Field(default_factory=dict)
    confidence: ReportConfidence
    limitations: List[str] = Field(default_factory=list)
    evidence_references: List[EvidenceReference] = Field(default_factory=list)
    provider_id: Optional[str] = None


class ReportMetric(BaseModel):
    name: str
    value: float
    unit: str = ""
    sample_size: SampleSize
    detail: str = ""


class ReportRow(BaseModel):
    rank: int = Field(ge=1, default=1)
    label: str
    value: float = 0.0
    count: int = Field(ge=0, default=0)
    sample_size: SampleSize
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TimeSeriesPoint(BaseModel):
    timestamp: str
    value: float
    sample_size: SampleSize
    label: str = ""


class ResearchReport(BaseModel):
    metadata: ReportMetadata
    summary: str
    metrics: List[ReportMetric] = Field(default_factory=list)
    rows: List[ReportRow] = Field(default_factory=list)
    series: List[TimeSeriesPoint] = Field(default_factory=list)


class ResearchDashboard(BaseModel):
    generated_at: str
    schema_version: str = RESEARCH_SCHEMA_VERSION
    engine_version: str = RESEARCH_ENGINE_VERSION
    registry_version: str = ""
    provider_versions: Dict[str, str] = Field(default_factory=dict)
    time_window: TimeWindow
    reports: Dict[str, ResearchReport] = Field(default_factory=dict)
    limitations: List[str] = Field(default_factory=list)


class ReportCatalogEntry(BaseModel):
    report_type: ResearchReportType
    label: str
    description: str


def assert_no_causation_language(text: str) -> None:
    lowered = text.lower()
    for term in CAUSATION_FORBIDDEN:
        if term in lowered:
            raise ValueError(f"Report text must not imply causation (found '{term}')")
