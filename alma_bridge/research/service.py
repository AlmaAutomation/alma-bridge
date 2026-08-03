"""Research platform orchestration — read-only report generation."""

from __future__ import annotations

from typing import List, Optional

from alma_bridge.research.models import (
    REPORT_TYPE_LABELS,
    ResearchDashboard,
    ResearchReport,
    ResearchReportType,
    TimeWindow,
    utc_now_iso,
)
from alma_bridge.research.queries import ResearchQueries
from alma_bridge.research.reports import ReportGenerator
from alma_bridge.research.repository import ResearchRepository


DASHBOARD_REPORT_TYPES = (
    ResearchReportType.TOP_UNSUPPORTED_BEHAVIORS,
    ResearchReportType.TOP_CALIBRATION_GAPS,
    ResearchReportType.UNKNOWN_APIS,
    ResearchReportType.CAPABILITY_MATURITY_GROWTH,
    ResearchReportType.PREDICTION_ACCURACY_OVER_TIME,
    ResearchReportType.NATIVE_RUNTIME_GROWTH,
    ResearchReportType.GOVERNANCE_VELOCITY,
    ResearchReportType.EXPANSION_BACKLOG,
    ResearchReportType.VERIFICATION_TRENDS,
)


class ResearchService:
    """Orchestrate deterministic research report generation."""

    _instance: Optional[ResearchService] = None

    def __init__(
        self,
        *,
        queries: Optional[ResearchQueries] = None,
        generator: Optional[ReportGenerator] = None,
        repository: Optional[ResearchRepository] = None,
    ) -> None:
        self._queries = queries or ResearchQueries()
        self._generator = generator or ReportGenerator(self._queries)
        self._repo = repository or ResearchRepository()

    @classmethod
    def shared(cls) -> ResearchService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def list_report_types(self) -> List[dict]:
        return self._generator.catalog()

    def generate_report(
        self,
        report_type: ResearchReportType,
        *,
        time_start: Optional[str] = None,
        time_end: Optional[str] = None,
        provider_id: Optional[str] = None,
        use_cache: bool = False,
    ) -> ResearchReport:
        window = self._queries.time_window_from_params(start=time_start, end=time_end)
        cache_key = self._repo.cache_key(report_type.value, window.label, provider_id)
        if use_cache:
            cached = self._repo.get_cached(cache_key)
            if cached is not None:
                return cached
        report = self._generator.generate(report_type, window, provider_id=provider_id)
        if use_cache:
            self._repo.save_cache(cache_key, report)
        return report

    def generate_dashboard(
        self,
        *,
        time_start: Optional[str] = None,
        time_end: Optional[str] = None,
        provider_id: Optional[str] = None,
    ) -> ResearchDashboard:
        window = self._queries.time_window_from_params(start=time_start, end=time_end)
        reports: dict[str, ResearchReport] = {}
        limitations: list[str] = []
        for report_type in DASHBOARD_REPORT_TYPES:
            try:
                report = self.generate_report(
                    report_type,
                    time_start=time_start,
                    time_end=time_end,
                    provider_id=provider_id,
                )
                reports[report_type.value] = report
                limitations.extend(report.metadata.limitations)
            except Exception:
                limitations.append(f"report_unavailable:{report_type.value}")
        return ResearchDashboard(
            generated_at=utc_now_iso(),
            registry_version=self._queries.registry_version(),
            provider_versions=self._queries.provider_versions(),
            time_window=window,
            reports=reports,
            limitations=sorted(set(limitations)),
        )

    @staticmethod
    def parse_report_type(value: str) -> ResearchReportType:
        try:
            return ResearchReportType(value)
        except ValueError as exc:
            valid = ", ".join(rt.value for rt in ResearchReportType)
            raise ValueError(f"Unknown report type '{value}'. Valid: {valid}") from exc

    @staticmethod
    def report_label(report_type: ResearchReportType) -> str:
        return REPORT_TYPE_LABELS[report_type]
