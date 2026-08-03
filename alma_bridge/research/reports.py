"""Report generators — one deterministic report per type."""

from __future__ import annotations

from typing import List, Optional

from alma_bridge.research.analytics import EvidenceAnalytics, compute_confidence
from alma_bridge.research.correlation import CorrelationAnalytics
from alma_bridge.research.digest import compute_report_digest
from alma_bridge.research.evolution import EvolutionAnalytics
from alma_bridge.research.models import (
    REPORT_TYPE_LABELS,
    EvidenceReference,
    ReportConfidence,
    ReportMetadata,
    ReportMetric,
    ReportRow,
    ResearchReport,
    ResearchReportType,
    SampleSize,
    TimeWindow,
    assert_no_causation_language,
    utc_now_iso,
)
from alma_bridge.research.queries import ResearchQueries
from alma_bridge.research.trend_analysis import TrendAnalysis


class ReportGenerator:
    """Generate deterministic research reports from read-only evidence."""

    def __init__(self, queries: Optional[ResearchQueries] = None) -> None:
        self._queries = queries or ResearchQueries()
        self._analytics = EvidenceAnalytics(self._queries)
        self._trends = TrendAnalysis(self._queries)
        self._evolution = EvolutionAnalytics(self._queries)
        self._correlation = CorrelationAnalytics(self._queries)

    def _base_metadata(
        self,
        report_type: ResearchReportType,
        sample_size: SampleSize,
        window: TimeWindow,
        *,
        provider_id: Optional[str] = None,
        limitations: Optional[List[str]] = None,
        evidence_refs: Optional[List[EvidenceReference]] = None,
    ) -> ReportMetadata:
        score, factors = compute_confidence(sample_size.numerator, sample_size.denominator)
        return ReportMetadata(
            report_type=report_type,
            report_digest="",
            generated_at=utc_now_iso(),
            sample_size=sample_size,
            time_window=window,
            registry_version=self._queries.registry_version(),
            provider_versions=self._queries.provider_versions(),
            confidence=ReportConfidence(
                score=score,
                basis="deterministic_sample_coverage",
                factors=factors,
            ),
            limitations=limitations or [],
            evidence_references=evidence_refs or [],
            provider_id=provider_id,
        )

    def _finalize(self, report: ResearchReport) -> ResearchReport:
        assert_no_causation_language(report.summary)
        digest = compute_report_digest(report)
        return report.model_copy(
            update={"metadata": report.metadata.model_copy(update={"report_digest": digest})}
        )

    def generate(
        self,
        report_type: ResearchReportType,
        window: TimeWindow,
        *,
        provider_id: Optional[str] = None,
    ) -> ResearchReport:
        generators = {
            ResearchReportType.TOP_UNSUPPORTED_BEHAVIORS: self._top_unsupported_behaviors,
            ResearchReportType.TOP_CALIBRATION_GAPS: self._top_calibration_gaps,
            ResearchReportType.UNKNOWN_APIS: self._unknown_apis,
            ResearchReportType.CAPABILITY_MATURITY_GROWTH: self._capability_maturity_growth,
            ResearchReportType.PREDICTION_ACCURACY_OVER_TIME: self._prediction_accuracy,
            ResearchReportType.BEHAVIOR_COVERAGE_EVOLUTION: self._behavior_coverage,
            ResearchReportType.NATIVE_RUNTIME_GROWTH: self._native_runtime_growth,
            ResearchReportType.GOVERNANCE_VELOCITY: self._governance_velocity,
            ResearchReportType.EXPANSION_BACKLOG: self._expansion_backlog,
            ResearchReportType.VERIFICATION_TRENDS: self._verification_trends,
        }
        generator = generators.get(report_type)
        if generator is None:
            raise ValueError(f"Unknown report type: {report_type}")
        return self._finalize(generator(window, provider_id=provider_id))

    def _top_unsupported_behaviors(
        self, window: TimeWindow, *, provider_id: Optional[str] = None
    ) -> ResearchReport:
        counts, denominator = self._analytics.unsupported_behavior_counts(
            window, provider_id=provider_id
        )
        rows: List[ReportRow] = []
        for rank, (label, count) in enumerate(counts.most_common(20), start=1):
            rows.append(
                ReportRow(
                    rank=rank,
                    label=label,
                    count=count,
                    value=round(count / max(denominator, 1), 4),
                    sample_size=SampleSize(numerator=count, denominator=denominator),
                )
            )
        sample = SampleSize(
            numerator=sum(counts.values()),
            denominator=max(denominator, sum(counts.values())),
            label="unsupported_behavior_observations",
        )
        limitations = []
        if sample.numerator == 0:
            limitations.append("no_unsupported_behavior_observations_in_window")
        report = ResearchReport(
            metadata=self._base_metadata(
                ResearchReportType.TOP_UNSUPPORTED_BEHAVIORS,
                sample,
                window,
                provider_id=provider_id,
                limitations=limitations,
                evidence_refs=[
                    EvidenceReference(source="aci_behavior_registry", artifact_id="profiles"),
                    EvidenceReference(source="aci_calibration", artifact_id="records"),
                ],
            ),
            summary=(
                f"Observed {sample.numerator} unsupported behavior occurrences "
                f"across {denominator} profile/analysis contexts. "
                "Rankings describe frequency, not causation."
            ),
            rows=rows,
            metrics=[
                ReportMetric(
                    name="distinct_unsupported_behaviors",
                    value=float(len(counts)),
                    unit="count",
                    sample_size=sample,
                )
            ],
        )
        return report

    def _top_calibration_gaps(
        self, window: TimeWindow, *, provider_id: Optional[str] = None
    ) -> ResearchReport:
        counts, total = self._analytics.calibration_gap_counts(window, provider_id=provider_id)
        rows = [
            ReportRow(
                rank=rank,
                label=label,
                count=count,
                value=round(count / max(total, 1), 4),
                sample_size=SampleSize(numerator=count, denominator=max(total, 1)),
            )
            for rank, (label, count) in enumerate(counts.most_common(20), start=1)
        ]
        fp_counts, fp_total = self._correlation.false_positive_by_behavior(
            window, provider_id=provider_id
        )
        sample = SampleSize(numerator=sum(counts.values()), denominator=max(total, 1))
        limitations = ["descriptive_ranking_not_causal"]
        if total == 0:
            limitations.append("no_calibration_records_in_window")
        return ResearchReport(
            metadata=self._base_metadata(
                ResearchReportType.TOP_CALIBRATION_GAPS,
                sample,
                window,
                provider_id=provider_id,
                limitations=limitations,
                evidence_refs=[EvidenceReference(source="aci_calibration", artifact_id="records")],
            ),
            summary=(
                f"Observed {total} calibration records; "
                f"{fp_total} false positives associated with behavior gaps. "
                "Gaps are ranked by observed frequency."
            ),
            rows=rows,
            metrics=[
                ReportMetric(
                    name="false_positive_behavior_associations",
                    value=float(sum(fp_counts.values())),
                    unit="count",
                    sample_size=SampleSize(numerator=fp_total, denominator=max(total, 1)),
                    detail="observed correlation with behavior gaps",
                )
            ],
        )

    def _unknown_apis(
        self, window: TimeWindow, *, provider_id: Optional[str] = None
    ) -> ResearchReport:
        counts, total = self._analytics.unknown_api_counts(window)
        rows = [
            ReportRow(
                rank=rank,
                label=label,
                count=count,
                value=round(count / max(total, 1), 4),
                sample_size=SampleSize(numerator=count, denominator=max(total, 1)),
            )
            for rank, (label, count) in enumerate(counts.most_common(25), start=1)
        ]
        sample = SampleSize(numerator=sum(counts.values()), denominator=max(total, 1))
        limitations = []
        if total == 0:
            limitations.append("no_analyses_in_window")
        return ResearchReport(
            metadata=self._base_metadata(
                ResearchReportType.UNKNOWN_APIS,
                sample,
                window,
                provider_id=provider_id,
                limitations=limitations,
                evidence_refs=[EvidenceReference(source="aci_analysis", artifact_id="imports")],
            ),
            summary=(
                f"Observed {sample.numerator} unknown API import occurrences "
                f"across {total} total imports analyzed."
            ),
            rows=rows,
            metrics=[
                ReportMetric(
                    name="distinct_unknown_apis",
                    value=float(len(counts)),
                    unit="count",
                    sample_size=sample,
                )
            ],
        )

    def _capability_maturity_growth(
        self, window: TimeWindow, *, provider_id: Optional[str] = None
    ) -> ResearchReport:
        series, total = self._evolution.capability_maturity_growth(window)
        sample = SampleSize(numerator=len(series), denominator=max(total, 1))
        return ResearchReport(
            metadata=self._base_metadata(
                ResearchReportType.CAPABILITY_MATURITY_GROWTH,
                sample,
                window,
                provider_id=provider_id,
                evidence_refs=[
                    EvidenceReference(source="aci_governance", artifact_id="registry_versions")
                ],
            ),
            summary=(
                f"Capability maturity tracked across {len(series)} registry snapshots "
                f"with {total} total entries observed."
            ),
            series=series,
            metrics=[
                ReportMetric(
                    name="registry_entry_count",
                    value=float(total),
                    unit="count",
                    sample_size=sample,
                )
            ],
        )

    def _prediction_accuracy(
        self, window: TimeWindow, *, provider_id: Optional[str] = None
    ) -> ResearchReport:
        series, total = self._trends.prediction_accuracy_over_time(window, provider_id=provider_id)
        correct = sum(p.sample_size.numerator for p in series)
        sample = SampleSize(numerator=correct, denominator=max(total, 1))
        limitations = ["accuracy_is_descriptive_not_predictive"]
        if total == 0:
            limitations.append("no_calibration_records_in_window")
        return ResearchReport(
            metadata=self._base_metadata(
                ResearchReportType.PREDICTION_ACCURACY_OVER_TIME,
                sample,
                window,
                provider_id=provider_id,
                limitations=limitations,
                evidence_refs=[EvidenceReference(source="aci_calibration", artifact_id="records")],
            ),
            summary=(
                f"Prediction accuracy observed over {len(series)} time buckets "
                f"from {total} authoritative calibration records."
            ),
            series=series,
            metrics=[
                ReportMetric(
                    name="overall_accuracy",
                    value=round(correct / max(total, 1), 4),
                    unit="ratio",
                    sample_size=sample,
                )
            ],
        )

    def _behavior_coverage(
        self, window: TimeWindow, *, provider_id: Optional[str] = None
    ) -> ResearchReport:
        series, total = self._trends.behavior_coverage_evolution(window)
        sample = SampleSize(numerator=len(series), denominator=max(total, 1))
        return ResearchReport(
            metadata=self._base_metadata(
                ResearchReportType.BEHAVIOR_COVERAGE_EVOLUTION,
                sample,
                window,
                provider_id=provider_id,
                evidence_refs=[
                    EvidenceReference(source="aci_behavior_registry", artifact_id="profiles")
                ],
            ),
            summary=(
                f"Behavior coverage evolution observed across {len(series)} snapshots "
                f"from {total} behavior definitions."
            ),
            series=series,
        )

    def _native_runtime_growth(
        self, window: TimeWindow, *, provider_id: Optional[str] = None
    ) -> ResearchReport:
        series, cap_count = self._trends.native_runtime_growth(window)
        sample = SampleSize(numerator=len(series), denominator=max(cap_count, 1))
        snap = self._analytics.registry_snapshot()
        return ResearchReport(
            metadata=self._base_metadata(
                ResearchReportType.NATIVE_RUNTIME_GROWTH,
                sample,
                window,
                provider_id=provider_id,
                evidence_refs=[EvidenceReference(source="aci_registry", artifact_id="capabilities")],
            ),
            summary=(
                f"NativeAlmaRuntime growth observed across {len(series)} points; "
                f"{int(snap.get('native_supported_capabilities', 0))} capabilities "
                f"currently native-supported of {int(snap.get('capability_count', 0))}."
            ),
            series=series,
            metrics=[
                ReportMetric(
                    name="native_supported_capabilities",
                    value=snap.get("native_supported_capabilities", 0.0),
                    unit="count",
                    sample_size=SampleSize(
                        numerator=int(snap.get("native_supported_capabilities", 0)),
                        denominator=int(snap.get("capability_count", 1)),
                    ),
                )
            ],
        )

    def _governance_velocity(
        self, window: TimeWindow, *, provider_id: Optional[str] = None
    ) -> ResearchReport:
        series, total = self._evolution.governance_velocity(window)
        sample = SampleSize(numerator=total, denominator=max(total, 1))
        limitations = []
        if total == 0:
            limitations.append("no_governance_proposals_in_window")
        return ResearchReport(
            metadata=self._base_metadata(
                ResearchReportType.GOVERNANCE_VELOCITY,
                sample,
                window,
                provider_id=provider_id,
                limitations=limitations,
                evidence_refs=[EvidenceReference(source="aci_governance", artifact_id="proposals")],
            ),
            summary=(
                f"Governance velocity: {total} proposals observed across "
                f"{len(series)} time buckets."
            ),
            series=series,
            metrics=[
                ReportMetric(
                    name="proposal_count",
                    value=float(total),
                    unit="count",
                    sample_size=sample,
                )
            ],
        )

    def _expansion_backlog(
        self, window: TimeWindow, *, provider_id: Optional[str] = None
    ) -> ResearchReport:
        total, completed, backlog = self._evolution.expansion_completion(window)
        sample = SampleSize(numerator=completed, denominator=max(total, 1))
        limitations = ["expansion_candidates_are_planning_artifacts_not_completion_tracked"]
        if total == 0:
            limitations.append("no_expansion_plan_available")
        return ResearchReport(
            metadata=self._base_metadata(
                ResearchReportType.EXPANSION_BACKLOG,
                sample,
                window,
                provider_id=provider_id,
                limitations=limitations,
                evidence_refs=[EvidenceReference(source="aci_expansion", artifact_id="latest_plan")],
            ),
            summary=(
                f"Expansion backlog: {backlog} of {total} candidates remain open; "
                f"{completed} marked completed."
            ),
            metrics=[
                ReportMetric(
                    name="backlog_size",
                    value=float(backlog),
                    unit="count",
                    sample_size=sample,
                ),
                ReportMetric(
                    name="completion_rate",
                    value=round(completed / max(total, 1), 4),
                    unit="ratio",
                    sample_size=sample,
                ),
            ],
        )

    def _verification_trends(
        self, window: TimeWindow, *, provider_id: Optional[str] = None
    ) -> ResearchReport:
        series, total = self._trends.verification_trends(window)
        verified, failed, _ = self._analytics.verification_outcomes(window)
        sample = SampleSize(numerator=verified, denominator=max(total, 1))
        limitations = []
        if total == 0:
            limitations.append("no_verification_events_in_window")
        return ResearchReport(
            metadata=self._base_metadata(
                ResearchReportType.VERIFICATION_TRENDS,
                sample,
                window,
                provider_id=provider_id,
                limitations=limitations,
                evidence_refs=[
                    EvidenceReference(source="evidence_timeline", artifact_id="VerificationCompleted")
                ],
            ),
            summary=(
                f"Verification trends from {total} timeline events: "
                f"{verified} verified, {failed} not verified."
            ),
            series=series,
            metrics=[
                ReportMetric(
                    name="verification_success_rate",
                    value=round(verified / max(total, 1), 4),
                    unit="ratio",
                    sample_size=sample,
                )
            ],
        )

    def catalog(self) -> list:
        return [
            {
                "report_type": rt.value,
                "label": REPORT_TYPE_LABELS[rt],
                "description": f"Deterministic {REPORT_TYPE_LABELS[rt].lower()} report from evidence.",
            }
            for rt in ResearchReportType
        ]
