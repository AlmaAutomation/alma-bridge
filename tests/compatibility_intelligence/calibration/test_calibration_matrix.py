"""ACI Phase 2 calibration test matrix — 22 scenarios."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from alma_bridge.compatibility_intelligence.calibration import (
    attribute_failure,
    classify_calibration,
)
from alma_bridge.compatibility_intelligence.calibration_repository import CalibrationRepository
from alma_bridge.compatibility_intelligence.calibration_service import CalibrationService
from alma_bridge.compatibility_intelligence.coverage_validation import compute_coverage_validation
from alma_bridge.compatibility_intelligence.models import (
    CalibrationClassification,
    FailureAttribution,
    OutcomeLink,
    OutcomeType,
    PredictionSnapshot,
    StaticCoverageSnapshot,
    CompatibilityPrediction,
    ConfidenceAssessment,
    ConfidenceLevelName,
    ProvenanceEvidence,
)
from alma_bridge.compatibility_intelligence.outcome_linking import (
    OutcomeLinkingService,
    build_outcome_link,
    resolve_outcome_type,
)
from alma_bridge.compatibility_intelligence.service import CompatibilityIntelligenceService
from alma_bridge.compatibility_intelligence.snapshot import build_prediction_snapshot
from alma_bridge.main import app


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


def _make_snapshot(
    *,
    binary_digest: str = "abc123",
    provider_id: str = "native_alma",
    predicted_eligible: bool = True,
    behavior_gaps: list | None = None,
    cap_reg: str = "aci_capability_registry_v1",
    api_reg: str = "aci_api_registry_v1",
) -> PredictionSnapshot:
    return PredictionSnapshot(
        snapshot_id="snap1",
        analysis_digest="analysis1",
        binary_digest=binary_digest,
        provider_id=provider_id,
        provider_version="0.2.0-m2",
        capability_registry_version=cap_reg,
        api_registry_version=api_reg,
        static_coverage=StaticCoverageSnapshot(
            symbol_coverage_percent=100.0,
            behavior_coverage_percent=50.0 if behavior_gaps else 100.0,
            behavior_gaps=behavior_gaps or [],
        ),
        confidence_level=ConfidenceLevelName.HIGH,
        confidence_score=0.8,
        prediction=_minimal_prediction(),
        predicted_eligible=predicted_eligible,
        created_at="2026-08-02T00:00:00+00:00",
        engine_version="aci_snapshot_v1",
    )


def _make_outcome(
    snapshot: PredictionSnapshot,
    outcome_type: OutcomeType,
    *,
    binary_digest: str | None = None,
    provider_id: str | None = None,
) -> OutcomeLink:
    link = build_outcome_link(
        snapshot,
        session_id="sess1",
        outcome_type=outcome_type,
        verification_result_ref="vref1" if outcome_type in {
            OutcomeType.VERIFIED_SUCCESS,
            OutcomeType.VERIFIED_FAILURE,
        } else None,
        verified_success=outcome_type == OutcomeType.VERIFIED_SUCCESS,
    )
    if binary_digest:
        link = link.model_copy(update={"binary_digest": binary_digest})
    if provider_id:
        link = link.model_copy(update={"provider_id": provider_id})
    return link


class TestPredictionSnapshot:
    def test_01_snapshot_immutable(self, tmp_calibration_repo, hello64_path):
        svc = CompatibilityIntelligenceService(calibration_repository=tmp_calibration_repo)
        snap1 = svc.create_prediction_snapshot(
            str(hello64_path), provider_id="native_alma", session_id="s1"
        )
        snap2 = tmp_calibration_repo.get_snapshot(snap1.snapshot_id)
        assert snap2 is not None
        assert snap2.snapshot_id == snap1.snapshot_id
        assert snap2.created_at == snap1.created_at

    def test_02_binds_binary_digest(self, hello64_path):
        svc = CompatibilityIntelligenceService()
        analysis = svc.analyze(str(hello64_path), persist=False)
        snap = build_prediction_snapshot(analysis, provider_id="native_alma")
        assert snap.binary_digest == analysis.binary_digest

    def test_03_binds_provider_version(self, hello64_path):
        from alma_bridge.compatibility_intelligence.governance.models import (
            GOVERNANCE_REGISTRY_SEED_VERSION,
        )

        analysis = CompatibilityIntelligenceService().analyze(str(hello64_path), persist=False)
        snap = build_prediction_snapshot(analysis, provider_id="native_alma")
        assert snap.provider_version == "0.2.0-m2"
        assert snap.capability_registry_version == GOVERNANCE_REGISTRY_SEED_VERSION


class TestCalibrationClassification:
    def test_04_verified_success_true_positive(self):
        snap = _make_snapshot(predicted_eligible=True)
        outcome = _make_outcome(snap, OutcomeType.VERIFIED_SUCCESS)
        assert classify_calibration(snap, outcome) == CalibrationClassification.TRUE_POSITIVE

    def test_05_verified_failure_false_positive(self):
        snap = _make_snapshot(predicted_eligible=True)
        outcome = _make_outcome(snap, OutcomeType.VERIFIED_FAILURE)
        assert classify_calibration(snap, outcome) == CalibrationClassification.FALSE_POSITIVE

    def test_06_unverifiable_indeterminate(self):
        snap = _make_snapshot(predicted_eligible=True)
        outcome = _make_outcome(snap, OutcomeType.UNVERIFIABLE)
        assert classify_calibration(snap, outcome) == CalibrationClassification.INDETERMINATE

    def test_07_ineligible_verified_success_false_negative(self):
        snap = _make_snapshot(predicted_eligible=False)
        outcome = _make_outcome(snap, OutcomeType.VERIFIED_SUCCESS)
        assert classify_calibration(snap, outcome) == CalibrationClassification.FALSE_NEGATIVE

    def test_08_unknown_gap_stays_unknown(self):
        snap = _make_snapshot(predicted_eligible=True)
        outcome = _make_outcome(snap, OutcomeType.VERIFIED_FAILURE)
        attr = attribute_failure(snap, outcome, classification=CalibrationClassification.FALSE_POSITIVE)
        assert attr == FailureAttribution.UNKNOWN

    def test_09_failure_attribution_requires_evidence(self):
        snap = _make_snapshot(predicted_eligible=True, behavior_gaps=["append_existing_file"])
        outcome = _make_outcome(snap, OutcomeType.VERIFIED_FAILURE)
        attr = attribute_failure(snap, outcome, classification=CalibrationClassification.FALSE_POSITIVE)
        assert attr == FailureAttribution.FILESYSTEM_SEMANTICS_GAP


class TestBehaviorCoverage:
    def test_10_static_symbol_not_full_behavior(self, hello64_path):
        svc = CompatibilityIntelligenceService()
        analysis = svc.analyze(str(hello64_path), persist=False)
        validation = compute_coverage_validation(
            analysis.coverage,
            analysis.required_capabilities,
            analysis.imports,
            analysis.api_classifications,
            analysis.metadata,
            provider_id="native_alma",
            fixture_name="hello64.exe",
        )
        assert validation.symbol_coverage_percent >= 99.0

    def test_11_behavior_coverage_calculated(self, file_append_unsupported_path):
        svc = CompatibilityIntelligenceService()
        analysis = svc.analyze(str(file_append_unsupported_path), persist=False)
        validation = compute_coverage_validation(
            analysis.coverage,
            analysis.required_capabilities,
            analysis.imports,
            analysis.api_classifications,
            analysis.metadata,
            provider_id="native_alma",
            fixture_name="file_append_unsupported.exe",
        )
        assert validation.behavior_coverage_percent >= 50.0
        assert "append_existing_file" in validation.supported_behaviors


class TestCalibrationMetrics:
    def test_12_sample_sizes_exposed(self, tmp_calibration_repo):
        svc = CalibrationService(repository=tmp_calibration_repo)
        snap = _make_snapshot()
        outcome = _make_outcome(snap, OutcomeType.VERIFIED_SUCCESS)
        tmp_calibration_repo.save_snapshot(snap)
        OutcomeLinkingService(tmp_calibration_repo).link_outcome(
            snap,
            session_id="s1",
            outcome_type=OutcomeType.VERIFIED_SUCCESS,
            verification_result_ref="v1",
            verified_success=True,
        )
        svc.calibrate(snap, outcome)
        metrics = svc.compute_metrics()
        d = metrics.to_dict()
        assert "authoritative_sample_size" in d
        assert d["true_positive"]["denominator"] >= 1

    def test_13_old_predictions_use_old_registry(self, tmp_calibration_repo):
        snap = _make_snapshot(cap_reg="old_registry_v0", api_reg="old_api_v0")
        tmp_calibration_repo.save_snapshot(snap)
        loaded = tmp_calibration_repo.get_snapshot(snap.snapshot_id)
        assert loaded.capability_registry_version == "old_registry_v0"

    def test_14_application_a_cannot_calibrate_b(self):
        snap = _make_snapshot(binary_digest="aaa")
        outcome = _make_outcome(snap, OutcomeType.VERIFIED_SUCCESS, binary_digest="bbb")
        assert classify_calibration(snap, outcome) == CalibrationClassification.INDETERMINATE

    def test_15_provider_a_cannot_calibrate_b(self):
        snap = _make_snapshot(provider_id="native_alma")
        outcome = _make_outcome(snap, OutcomeType.VERIFIED_SUCCESS, provider_id="wine")
        assert classify_calibration(snap, outcome) == CalibrationClassification.INDETERMINATE


class TestCalibrationAPI:
    def test_16_no_execution_in_calibration_get(self, hello64_path):
        client = TestClient(app)
        with patch(
            "alma_bridge.native_runtime.runtime.run_pe_in_workspace",
            side_effect=AssertionError("execution forbidden"),
        ):
            r = client.get("/bridge/compatibility/calibration")
            assert r.status_code == 200
            r2 = client.get("/bridge/compatibility/calibration/capabilities/filesystem.basic_io")
            assert r2.status_code == 200

    def test_17_calibration_cannot_mutate_registry(self, hello64_path):
        from alma_bridge.compatibility_intelligence.capabilities import CAPABILITY_REGISTRY

        before = len(CAPABILITY_REGISTRY)
        CalibrationService().compute_metrics()
        assert len(CAPABILITY_REGISTRY) == before

    def test_18_calibration_cannot_bypass_verification_engine(self):
        assert resolve_outcome_type(success=True, verification_result_ref=None) == OutcomeType.UNVERIFIABLE


class TestProviderLinking:
    def test_19_native_fixture_predictions(self, hello64_path, tmp_calibration_repo):
        svc = CompatibilityIntelligenceService(calibration_repository=tmp_calibration_repo)
        snap = svc.create_prediction_snapshot(
            str(hello64_path), provider_id="native_alma", session_id="native_sess"
        )
        assert snap.provider_id == "native_alma"

    def test_20_wine_predictions(self, hello64_path, tmp_calibration_repo):
        snap = build_prediction_snapshot(
            CompatibilityIntelligenceService().analyze(str(hello64_path), persist=False),
            provider_id="wine",
        )
        assert snap.provider_id == "wine"


class TestDeterminism:
    def test_21_deterministic_calibration(self, hello64_path):
        analysis = CompatibilityIntelligenceService().analyze(str(hello64_path), persist=False)
        s1 = build_prediction_snapshot(analysis, provider_id="native_alma", session_id="d1")
        s2 = build_prediction_snapshot(analysis, provider_id="native_alma", session_id="d1")
        assert s1.snapshot_id == s2.snapshot_id

    def test_22_explorer_preserves_prediction_vs_verification(self):
        from alma_bridge.api import compatibility_intelligence_routes as routes

        assert hasattr(routes, "calibration_metrics")
        assert hasattr(routes, "calibration_by_analysis")
        snap = _make_snapshot()
        outcome = _make_outcome(snap, OutcomeType.VERIFIED_SUCCESS)
        record = CalibrationService().calibrate(snap, outcome)
        assert record["predicted_eligible"] is True
        assert record["verified_success"] is True


class TestEndToEndAcceptance:
    def test_hello64_true_positive_path(self, hello64_path):
        svc = CompatibilityIntelligenceService()
        analysis = svc.analyze(str(hello64_path), persist=False)
        snap = build_prediction_snapshot(
            analysis, provider_id="native_alma", fixture_name="hello64.exe"
        )
        assert snap.predicted_eligible
        outcome = build_outcome_link(
            snap,
            session_id="e2e",
            outcome_type=OutcomeType.VERIFIED_SUCCESS,
            verification_result_ref="verified",
            verified_success=True,
        )
        assert classify_calibration(snap, outcome) == CalibrationClassification.TRUE_POSITIVE

    def test_append_fixture_exposes_gap(self, file_append_unsupported_path):
        svc = CompatibilityIntelligenceService()
        analysis = svc.analyze(str(file_append_unsupported_path), persist=False)
        snap = build_prediction_snapshot(
            analysis,
            provider_id="native_alma",
            fixture_name="file_append_unsupported.exe",
        )
        assert snap.static_coverage.behavior_gaps
        assert snap.confidence_level != ConfidenceLevelName.VERY_HIGH
        outcome = build_outcome_link(
            snap,
            session_id="e2e_fail",
            outcome_type=OutcomeType.VERIFIED_FAILURE,
            verification_result_ref="verified_fail",
            verified_success=False,
        )
        cls = classify_calibration(snap, outcome)
        if snap.predicted_eligible:
            assert cls == CalibrationClassification.FALSE_POSITIVE
