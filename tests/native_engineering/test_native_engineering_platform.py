"""Native Runtime Engineering Platform verification."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alma_bridge.main import app
from alma_bridge.native_engineering.behavior_suites import get_all_behavior_suites
from alma_bridge.native_engineering.benchmarks import run_all_benchmarks, run_benchmark
from alma_bridge.native_engineering.conformance import generate_conformance_report
from alma_bridge.native_engineering.digest import digest_of
from alma_bridge.native_engineering.errors import HistoryMutationError
from alma_bridge.native_engineering.longitudinal import append_benchmark_result, merge_histories
from alma_bridge.native_engineering.models import BenchmarkHistory, BenchmarkMetric, BenchmarkResult, TestScenarioStatus
from alma_bridge.native_engineering.repository import NativeEngineeringRepository
from alma_bridge.native_engineering.specifications import get_all_specifications, get_specification, list_api_symbols

client = TestClient(app)

IMPLEMENTED_APIS = [
    "WriteFile",
    "CreateFileW",
    "ReadFile",
    "GetStdHandle",
    "ExitProcess",
    "GetEnvironmentVariableW",
    "GetCommandLineW",
    "CloseHandle",
    "GetLastError",
    "SetLastError",
    "GetModuleFileNameW",
    "GetCurrentProcessId",
    "Sleep",
]


class TestApiSpecifications:
    def test_all_implemented_apis_have_specs(self):
        symbols = list_api_symbols()
        assert len(symbols) == len(IMPLEMENTED_APIS)
        for api in IMPLEMENTED_APIS:
            assert api in symbols

    def test_specifications_are_deterministic(self):
        spec1 = get_specification("WriteFile")
        spec2 = get_specification("WriteFile")
        assert spec1.spec_digest == spec2.spec_digest
        assert spec1.spec_digest == digest_of(spec1.model_dump(mode="json", exclude={"spec_digest"}))

    def test_writefile_documents_overlapped_unsupported(self):
        spec = get_specification("WriteFile")
        assert "overlapped_io" in spec.unsupported_behaviors

    def test_createfilew_documents_append_unsupported(self):
        spec = get_specification("CreateFileW")
        assert "append_existing_file" in spec.unsupported_behaviors


class TestBehaviorSuites:
    def test_suites_cover_implemented_apis(self):
        suites = get_all_behavior_suites()
        assert set(suites.keys()) == set(IMPLEMENTED_APIS)

    def test_writefile_suite_scenarios(self):
        suite = get_all_behavior_suites()["WriteFile"]
        case_ids = {c.case_id for c in suite.cases}
        assert "writefile_console_stdout" in case_ids
        assert "writefile_overlapped_unsupported" in case_ids

    def test_append_unsupported_fixture_mapped(self):
        suite = get_all_behavior_suites()["CreateFileW"]
        append_case = next(c for c in suite.cases if c.case_id == "createfilew_append_unsupported")
        assert "file_append_unsupported.exe" in (append_case.fixture_path or "")
        assert append_case.status == TestScenarioStatus.PASS


class TestBenchmarks:
    def test_benchmark_without_execution_is_deterministic(self):
        r1 = run_benchmark("hello64.exe", allow_execution=False)
        r2 = run_benchmark("hello64.exe", allow_execution=False)
        assert r1.run_digest == r2.run_digest
        assert r1.metrics[0].value == 0.0

    def test_run_all_benchmarks_no_execution(self):
        results = run_all_benchmarks(allow_execution=False)
        assert len(results) == 9

    def test_reproducible_within_tolerance(self):
        results = run_all_benchmarks(allow_execution=False)
        for r in results:
            assert r.metrics[0].tolerance_percent >= 10.0


class TestConformance:
    def test_conformance_report_generated(self):
        report = generate_conformance_report()
        assert report.report_digest
        assert len(report.checks) >= 5
        statuses = {c.status for c in report.checks}
        assert TestScenarioStatus.PASS in statuses


class TestLongitudinal:
    def test_append_only_history(self):
        hist = BenchmarkHistory(benchmark_id="runtime_hello64")
        result = BenchmarkResult(
            benchmark_id="runtime_hello64",
            fixture_name="hello64.exe",
            metrics=[BenchmarkMetric(name="elapsed_ms", value=12.5)],
            run_digest="abc123",
        )
        updated = append_benchmark_result(hist, result)
        assert len(updated.points) == 1
        assert len(hist.points) == 0

    def test_merge_histories_appends_only(self):
        existing = [BenchmarkHistory(benchmark_id="b1", points=[])]
        result = BenchmarkResult(
            benchmark_id="b1",
            fixture_name="hello64.exe",
            metrics=[BenchmarkMetric(name="elapsed_ms", value=1.0)],
            run_digest="d1",
        )
        merged = merge_histories(existing, [result])
        assert len(merged[0].points) == 1


class TestRepository:
    def test_benchmark_result_append_only(self, engineering_tmp_paths):
        repo = NativeEngineeringRepository(store_dir=engineering_tmp_paths["engineering"])
        result = BenchmarkResult(
            benchmark_id="test_bench",
            fixture_name="hello64.exe",
            metrics=[BenchmarkMetric(name="elapsed_ms", value=5.0)],
            run_digest="unique_digest_1",
        )
        repo.save_benchmark_result(result)
        with pytest.raises(HistoryMutationError):
            repo.save_benchmark_result(result)


class TestServiceIntegration:
    def test_profiles_have_calibration_and_governance_links(self, engineering_service):
        profile = engineering_service.get_api_profile("WriteFile")
        assert profile.capability_id == "console.stdout"
        assert profile.specification.spec_digest
        assert profile.behavior_suite.cases

    def test_dashboard_aggregation(self, engineering_service):
        dashboard = engineering_service.engineering_dashboard()
        assert dashboard.api_count == len(IMPLEMENTED_APIS)
        assert dashboard.conformance_report.report_digest

    def test_evidence_links_resolve(self, engineering_service):
        profile = engineering_service.get_api_profile("CreateFileW")
        sources = {link.source for link in profile.evidence_links}
        assert "fixture" in sources
        assert "native-shim" in sources


class TestRoutes:
    def test_list_apis(self):
        res = client.get("/bridge/native-engineering/apis")
        assert res.status_code == 200
        data = res.json()
        assert data["count"] == len(IMPLEMENTED_APIS)

    def test_get_api_profile(self):
        res = client.get("/bridge/native-engineering/apis/WriteFile")
        assert res.status_code == 200
        assert res.json()["api_symbol"] == "WriteFile"

    def test_unknown_api_404(self):
        res = client.get("/bridge/native-engineering/apis/NotAnApi")
        assert res.status_code == 404

    def test_behaviors_dashboard(self):
        res = client.get("/bridge/native-engineering/behaviors")
        assert res.status_code == 200
        assert "entries" in res.json()

    def test_benchmarks_endpoint(self):
        res = client.get("/bridge/native-engineering/benchmarks")
        assert res.status_code == 200
        assert "catalog" in res.json()

    def test_conformance_endpoint(self):
        res = client.get("/bridge/native-engineering/conformance")
        assert res.status_code == 200

    def test_engineering_dashboard(self):
        res = client.get("/bridge/native-engineering/dashboard")
        assert res.status_code == 200
        assert res.json()["api_count"] == len(IMPLEMENTED_APIS)

    def test_get_endpoints_are_read_only(self):
        from alma_bridge.api import native_engineering_routes

        for route in native_engineering_routes.router.routes:
            assert route.methods == {"GET"}
