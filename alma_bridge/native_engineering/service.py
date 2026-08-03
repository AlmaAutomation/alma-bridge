"""Native Runtime Engineering Platform orchestration."""

from __future__ import annotations

from typing import List, Optional

from alma_bridge.native_engineering.benchmarks import run_all_benchmarks
from alma_bridge.native_engineering.dashboard import build_engineering_dashboard
from alma_bridge.native_engineering.longitudinal import merge_histories
from alma_bridge.native_engineering.models import (
    ApiEngineeringProfile,
    BehaviorCoverageDashboard,
    BenchmarkHistory,
    BenchmarkResult,
    ConformanceReport,
    EngineeringDashboard,
)
from alma_bridge.native_engineering.queries import NativeEngineeringQueries
from alma_bridge.native_engineering.repository import NativeEngineeringRepository


class NativeEngineeringService:
    """Orchestrate read-only engineering profiles and explicit benchmark recording."""

    _instance: Optional[NativeEngineeringService] = None

    def __init__(
        self,
        *,
        queries: Optional[NativeEngineeringQueries] = None,
        repository: Optional[NativeEngineeringRepository] = None,
    ) -> None:
        self._repo = repository or NativeEngineeringRepository()
        self._queries = queries or NativeEngineeringQueries(engineering_repo=self._repo)

    @classmethod
    def shared(cls) -> NativeEngineeringService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def list_api_profiles(self) -> List[ApiEngineeringProfile]:
        return self._queries.list_profiles()

    def get_api_profile(self, api_symbol: str) -> ApiEngineeringProfile:
        return self._queries.build_profile(api_symbol)

    def behavior_coverage(self) -> BehaviorCoverageDashboard:
        return self._queries.behavior_coverage_dashboard()

    def conformance_report(self) -> ConformanceReport:
        return self._queries.conformance_report()

    def benchmark_results_and_history(self) -> dict:
        results = self._repo.list_benchmark_results()
        history = self._queries.benchmark_history()
        return {
            "results": results,
            "history": history,
            "catalog": self._queries.list_benchmark_catalog(),
        }

    def engineering_dashboard(self) -> EngineeringDashboard:
        return build_engineering_dashboard(self._queries)

    def record_benchmarks(self, *, allow_execution: bool = False) -> List[BenchmarkResult]:
        """Explicit benchmark run — never called from GET endpoints."""
        results = run_all_benchmarks(allow_execution=allow_execution)
        for result in results:
            if result.run_digest and result.metrics[0].value > 0:
                try:
                    self._repo.save_benchmark_result(result)
                except Exception:
                    pass
        history = merge_histories(self._repo.list_benchmark_history(), results)
        for h in history:
            self._repo.save_benchmark_history(h)
        return results
