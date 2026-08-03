"""Research platform verification — deterministic, read-only, sample-sized."""

from __future__ import annotations

from fastapi.testclient import TestClient

from alma_bridge.compatibility_intelligence.models import (
    CalibrationClassification,
    OutcomeLink,
    OutcomeType,
    PredictionSnapshot,
    StaticCoverageSnapshot,
    CompatibilityPrediction,
    ConfidenceAssessment,
    ConfidenceLevelName,
    ProvenanceEvidence,
)
from alma_bridge.compatibility_intelligence.service import CompatibilityIntelligenceService
from alma_bridge.main import app
from alma_bridge.research.models import ResearchReportType, assert_no_causation_language
from alma_bridge.research.service import ResearchService

client = TestClient(app)


def _minimal_prediction(**kwargs) -> CompatibilityPrediction:
    return CompatibilityPrediction(
        native_compatible=kwargs.get("native_compatible", True),
        wine_compatible=kwargs.get("wine_compatible", True),
        needs_unsupported_apis=False,
        confidence=ConfidenceAssessment(
            level=ConfidenceLevelName.HIGH,
            score=0.8,
            factors=[],
            provenance=ProvenanceEvidence(source="test", artifact_id="test"),
        ),
    )


def _seed_calibration_record(calibration_repo, *, behavior_gaps=None, classification="false_positive"):
    snapshot = PredictionSnapshot(
        snapshot_id="snap_research_1",
        analysis_digest="analysis_research_1",
        binary_digest="binary_research_1",
        provider_id="native_alma",
        provider_version="0.2.0-m2",
        capability_registry_version="aci_capability_registry_v1",
        api_registry_version="aci_api_registry_v1",
        static_coverage=StaticCoverageSnapshot(
            symbol_coverage_percent=80.0,
            behavior_coverage_percent=50.0,
            behavior_gaps=behavior_gaps or ["append_existing_file"],
        ),
        confidence_level=ConfidenceLevelName.HIGH,
        confidence_score=0.8,
        prediction=_minimal_prediction(),
        predicted_eligible=True,
        created_at="2026-08-01T12:00:00+00:00",
        engine_version="aci_snapshot_v1",
    )
    calibration_repo.save_snapshot(snapshot)
    outcome = OutcomeLink(
        outcome_id="outcome_research_1",
        snapshot_id=snapshot.snapshot_id,
        session_id="session_research_1",
        binary_digest="binary_research_1",
        analysis_digest="analysis_research_1",
        provider_id="native_alma",
        provider_version="0.2.0-m2",
        outcome_type=OutcomeType.VERIFIED_FAILURE,
        verified_success=False,
        created_at="2026-08-01T12:05:00+00:00",
        engine_version="aci_calibration_v1",
    )
    calibration_repo.save_json_artifact("outcomes", outcome.outcome_id, outcome.model_dump(mode="json"))
    service = __import__(
        "alma_bridge.compatibility_intelligence.calibration_service",
        fromlist=["CalibrationService"],
    ).CalibrationService(calibration_repo)
    return service.calibrate(snapshot, outcome)


class TestReportGeneration:
    def test_all_report_types_generate(self, research_service):
        service, _evidence = research_service
        for report_type in ResearchReportType:
            report = service.generate_report(report_type)
            assert report.metadata.sample_size.denominator >= 0
            assert report.metadata.time_window.label
            assert report.metadata.confidence.basis
            assert report.metadata.report_digest
            assert report.summary

    def test_report_from_seeded_evidence(self, research_service, research_queries, hello64_path):
        service, evidence = research_service
        aci_repo = research_queries._analysis
        aci = CompatibilityIntelligenceService(repository=aci_repo)
        aci.analyze(str(hello64_path), persist=True)
        evidence.assemble_for_file(str(hello64_path), persist=True)

        _seed_calibration_record(research_queries._calibration_repo)

        report = service.generate_report(ResearchReportType.TOP_CALIBRATION_GAPS)
        assert report.metadata.sample_size.numerator >= 1
        assert len(report.rows) >= 1

    def test_deterministic_digest(self, research_service):
        service, _ = research_service
        r1 = service.generate_report(ResearchReportType.NATIVE_RUNTIME_GROWTH)
        r2 = service.generate_report(ResearchReportType.NATIVE_RUNTIME_GROWTH)
        assert r1.metadata.report_digest == r2.metadata.report_digest

    def test_empty_evidence_graceful(self, research_service):
        service, _ = research_service
        report = service.generate_report(ResearchReportType.VERIFICATION_TRENDS)
        assert "no_verification_events_in_window" in report.metadata.limitations or report.series == []

    def test_no_causation_in_summaries(self, research_service):
        service, _ = research_service
        for report_type in ResearchReportType:
            report = service.generate_report(report_type)
            assert_no_causation_language(report.summary)

    def test_time_window_filtering(self, research_service):
        service, _ = research_service
        report = service.generate_report(
            ResearchReportType.PREDICTION_ACCURACY_OVER_TIME,
            time_start="2099-01-01T00:00:00+00:00",
        )
        assert report.metadata.time_window.start.startswith("2099")

    def test_provider_scoped_report(self, research_service):
        service, _ = research_service
        report = service.generate_report(
            ResearchReportType.TOP_UNSUPPORTED_BEHAVIORS,
            provider_id="native_alma",
        )
        assert report.metadata.provider_id == "native_alma"


class TestResearchRoutes:
    def test_list_reports(self):
        res = client.get("/bridge/research/reports")
        assert res.status_code == 200
        data = res.json()
        assert len(data["report_types"]) == 10

    def test_get_report_by_type(self):
        res = client.get("/bridge/research/reports/native_runtime_growth")
        assert res.status_code == 200
        body = res.json()
        assert body["metadata"]["sample_size"]["denominator"] >= 0
        assert body["metadata"]["report_digest"]

    def test_unknown_report_type_404(self):
        res = client.get("/bridge/research/reports/not_a_real_report")
        assert res.status_code == 404

    def test_dashboard(self):
        res = client.get("/bridge/research/dashboard")
        assert res.status_code == 200
        data = res.json()
        assert "reports" in data
        assert "limitations" in data

    def test_get_endpoints_are_read_only(self):
        """Research routes register only GET handlers."""
        from alma_bridge.api import research_routes

        for route in research_routes.router.routes:
            assert route.methods == {"GET"}


class TestResearchIntegrity:
    def test_no_registry_mutation_on_report(self, research_service, research_queries):
        service, _ = research_service
        before = research_queries.registry_version()
        service.generate_report(ResearchReportType.CAPABILITY_MATURITY_GROWTH)
        after = research_queries.registry_version()
        assert before == after

    def test_dashboard_includes_key_reports(self, research_service):
        service, _ = research_service
        dashboard = service.generate_dashboard()
        assert ResearchReportType.TOP_UNSUPPORTED_BEHAVIORS.value in dashboard.reports
        assert ResearchReportType.VERIFICATION_TRENDS.value in dashboard.reports

    def test_sample_size_always_present(self, research_service):
        service, _ = research_service
        dashboard = service.generate_dashboard()
        for report in dashboard.reports.values():
            assert report.metadata.sample_size.denominator >= 0
            for metric in report.metrics:
                assert metric.sample_size.denominator >= 0

    def test_parse_report_type(self):
        rt = ResearchService.parse_report_type("governance_velocity")
        assert rt == ResearchReportType.GOVERNANCE_VELOCITY
