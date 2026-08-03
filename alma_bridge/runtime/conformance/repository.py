"""In-memory conformance report repository."""

from __future__ import annotations

from typing import Dict, List, Optional

from alma_bridge.runtime.conformance.models import ConformanceReport, ConformanceRunResult


class ConformanceRepository:
    def __init__(self) -> None:
        self._reports: Dict[str, ConformanceReport] = {}

    def save_report(self, report: ConformanceReport) -> None:
        self._reports[report.report_id] = report

    def get_report(self, report_id: str) -> Optional[ConformanceReport]:
        return self._reports.get(report_id)

    def list_reports(self) -> List[ConformanceReport]:
        return list(self._reports.values())
