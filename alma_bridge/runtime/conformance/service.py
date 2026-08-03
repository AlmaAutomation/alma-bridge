"""Runtime conformance service."""

from __future__ import annotations

from typing import List, Optional

from alma_bridge.runtime.conformance.models import ConformanceClassification, ConformanceReport
from alma_bridge.runtime.conformance.repository import ConformanceRepository
from alma_bridge.runtime.conformance.runner import ConformanceRunner
from alma_bridge.runtime.conformance.scenarios import list_scenarios
from alma_bridge.runtime.registry import RuntimeRegistry, build_default_registry


class ConformanceService:
    def __init__(
        self,
        registry: Optional[RuntimeRegistry] = None,
        repository: Optional[ConformanceRepository] = None,
    ) -> None:
        self._registry = registry or build_default_registry()
        self._repository = repository or ConformanceRepository()
        self._runner = ConformanceRunner(self._registry)

    def run_default_suite(
        self,
        *,
        report_id: str = "default",
        file_path: Optional[str] = None,
    ) -> ConformanceReport:
        results = [
            self._runner.run_scenario(scenario, file_path=file_path)
            for scenario in list_scenarios()
        ]
        summary: dict[str, int] = {}
        for result in results:
            key = result.classification.value
            summary[key] = summary.get(key, 0) + 1
        report = ConformanceReport(report_id=report_id, results=results, summary=summary)
        self._repository.save_report(report)
        return report

    def list_classifications(self) -> List[str]:
        return [item.value for item in ConformanceClassification]
