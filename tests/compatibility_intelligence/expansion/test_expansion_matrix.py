"""ACI Phase 4 expansion planning test matrix — 20 scenarios."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from alma_bridge.compatibility_intelligence.calibration_service import CalibrationService
from alma_bridge.compatibility_intelligence.expansion.complexity import assess_complexity
from alma_bridge.compatibility_intelligence.expansion.demand import DemandAggregator
from alma_bridge.compatibility_intelligence.expansion.ranking import (
    HARD_EXCLUDED_CAPABILITIES,
    is_hard_excluded,
)
from alma_bridge.compatibility_intelligence.expansion.service import ExpansionPlanningService
from alma_bridge.compatibility_intelligence.governance.models import (
    CapabilityMaturityEntry,
    CapabilityMaturityState,
    CapabilityScope,
)
from alma_bridge.compatibility_intelligence.models import (
    ACI_SCHEMA_VERSION,
    CompatibilityGraph,
    ApiClassificationResult,
    ApiComplexity,
    CapabilityRequirement,
    CompatibilityAnalysisResult,
    CompatibilityPrediction,
    ConfidenceAssessment,
    ConfidenceLevelName,
    CoverageReport,
    ImplementationStatus,
    OutcomeType,
    PeAnalysisMetadata,
    ProvenanceEvidence,
    ProviderCoverageBreakdown,
)
from alma_bridge.compatibility_intelligence.outcome_linking import build_outcome_link
from alma_bridge.compatibility_intelligence.service import CompatibilityIntelligenceService
from alma_bridge.compatibility_intelligence.snapshot import build_prediction_snapshot
from alma_bridge.main import app


def _provenance() -> ProvenanceEvidence:
    return ProvenanceEvidence(source="test", artifact_id="expansion_test")


def _metadata() -> PeAnalysisMetadata:
    return PeAnalysisMetadata(
        architecture="x64",
        subsystem="console",
        entry_point_rva=4096,
        image_size=8192,
        is_pe32_plus=True,
        has_tls=False,
        has_relocations=True,
        has_clr=False,
        has_manifest=False,
        has_debug=False,
        has_load_config=False,
        has_exception_directory=False,
        export_count=0,
    )


def _prediction(native_compatible: bool = False) -> CompatibilityPrediction:
    return CompatibilityPrediction(
        native_compatible=native_compatible,
        wine_compatible=True,
        needs_unsupported_apis=not native_compatible,
        confidence=ConfidenceAssessment(
            level=ConfidenceLevelName.MEDIUM,
            score=0.6,
            factors=[],
            provenance=_provenance(),
        ),
        potential_blockers=["behavior gap: append_existing_file"] if not native_compatible else [],
    )


def _coverage() -> CoverageReport:
    native = ProviderCoverageBreakdown(
        provider_id="native_alma",
        supported=3,
        partial=1,
        unsupported=0,
        total=4,
        coverage_percent=75.0,
        blockers=["append_existing_file"],
    )
    return CoverageReport(
        total_capabilities=1,
        total_apis=4,
        known_apis=4,
        unknown_apis=0,
        providers={
            "native_alma": native,
            "wine": native.model_copy(update={"provider_id": "wine", "coverage_percent": 100.0}),
        },
    )


def _append_analysis(
    *,
    binary_digest: str,
    analysis_id: str,
    file_path: str,
) -> CompatibilityAnalysisResult:
    return CompatibilityAnalysisResult(
        schema_version=ACI_SCHEMA_VERSION,
        analysis_id=analysis_id,
        file_path=file_path,
        binary_digest=binary_digest,
        metadata=_metadata(),
        imports=[],
        api_classifications=[
            ApiClassificationResult(
                dll="kernel32.dll",
                function="CreateFileW",
                capability_id="filesystem.basic_io",
                complexity=ApiComplexity.MEDIUM,
                native_status=ImplementationStatus.SUPPORTED,
                wine_status=ImplementationStatus.SUPPORTED,
                is_known=True,
                provenance=_provenance(),
            ),
            ApiClassificationResult(
                dll="kernel32.dll",
                function="WriteFile",
                capability_id="filesystem.basic_io",
                complexity=ApiComplexity.MEDIUM,
                native_status=ImplementationStatus.SUPPORTED,
                wine_status=ImplementationStatus.SUPPORTED,
                is_known=True,
                provenance=_provenance(),
            ),
        ],
        required_capabilities=[
            CapabilityRequirement(
                capability_id="filesystem.basic_io",
                description="File I/O",
                required_by_apis=["kernel32.dll!CreateFileW"],
            )
        ],
        coverage=_coverage(),
        prediction=_prediction(native_compatible=False),
        graph=CompatibilityGraph(),
        provenance=_provenance(),
    )


def _seed_open_existing_evidence(
    expansion_service: ExpansionPlanningService,
    *,
    sessions: int = 1,
    binary_digest: str = "readwrite_bin_1",
):
    analysis_repo = expansion_service._analysis_repo
    cal_repo = expansion_service._calibration_repo
    cal = CalibrationService(cal_repo)

    analysis = _append_analysis(
        binary_digest=binary_digest,
        analysis_id=f"analysis_{binary_digest}",
        file_path="/fixtures/file_read.exe",
    )
    analysis_repo.save(analysis)

    for i in range(sessions):
        session_id = f"readwrite_sess_{binary_digest}_{i}"
        snap = build_prediction_snapshot(
            analysis,
            provider_id="native_alma",
            session_id=session_id,
            fixture_name="file_read.exe",
        )
        static = snap.static_coverage.model_copy(
            update={
                "behavior_gaps": ["open_existing_readwrite"],
                "behavior_coverage_percent": 50.0,
            }
        )
        snap = snap.model_copy(update={"static_coverage": static, "predicted_eligible": False})
        cal_repo.save_snapshot(snap)
        outcome = build_outcome_link(
            snap,
            session_id=session_id,
            outcome_type=OutcomeType.VERIFIED_FAILURE,
            verification_result_ref="vref",
            verified_success=False,
        )
        cal.calibrate(snap, outcome)


def _seed_append_evidence(
    expansion_service: ExpansionPlanningService,
    *,
    sessions: int = 1,
    binary_digest: str = "append_bin_1",
):
    analysis_repo = expansion_service._analysis_repo
    cal_repo = expansion_service._calibration_repo
    cal = CalibrationService(cal_repo)

    analysis = _append_analysis(
        binary_digest=binary_digest,
        analysis_id=f"analysis_{binary_digest}",
        file_path="/fixtures/file_append_unsupported.exe",
    )
    analysis_repo.save(analysis)

    for i in range(sessions):
        session_id = f"append_sess_{binary_digest}_{i}"
        snap = build_prediction_snapshot(
            analysis,
            provider_id="native_alma",
            session_id=session_id,
            fixture_name="file_append_unsupported.exe",
        )
        static = snap.static_coverage.model_copy(
            update={"behavior_gaps": ["append_existing_file"], "behavior_coverage_percent": 50.0}
        )
        snap = snap.model_copy(update={"static_coverage": static, "predicted_eligible": False})
        cal_repo.save_snapshot(snap)
        outcome = build_outcome_link(
            snap,
            session_id=session_id,
            outcome_type=OutcomeType.VERIFIED_FAILURE,
            verification_result_ref="vref",
            verified_success=False,
        )
        cal.calibrate(snap, outcome)


class TestDemandDeduplication:
    def test_01_repeated_sessions_no_inflate(self, expansion_service):
        _seed_open_existing_evidence(expansion_service, sessions=5, binary_digest="same_bin")
        plan = expansion_service.generate_plan()
        candidates = [
            c for c in plan.ranked_candidates if c.behavior_id == "open_existing_readwrite"
        ]
        assert candidates, "expected open_existing_readwrite candidate"
        assert candidates[0].observed_demand_count == 1

    def test_02_app_a_cannot_affect_capability_b(self, expansion_service):
        _seed_append_evidence(expansion_service, binary_digest="bin_a")
        plan = expansion_service.generate_plan()
        unrelated = [c for c in plan.ranked_candidates if c.capability_id == "console.stdout"]
        assert unrelated == []


class TestProviderIsolation:
    def test_03_provider_a_demand_no_prioritize_b(self, expansion_service):
        _seed_append_evidence(expansion_service)
        plan = expansion_service.generate_plan()
        for c in plan.ranked_candidates:
            if c.capability_id == "filesystem.basic_io":
                assert c.provider_id == "native_alma"


class TestBehaviorCandidates:
    def test_04_unsupported_behavior_bounded_candidate(self, expansion_service):
        _seed_open_existing_evidence(expansion_service)
        plan = expansion_service.generate_plan()
        cand = next(c for c in plan.ranked_candidates if c.behavior_id == "open_existing_readwrite")
        assert cand.capability_id == "filesystem.basic_io"
        assert "open_existing" in cand.implementation_scope.lower()
        assert cand.dll_symbols

    def test_05_stable_behavior_excluded(self, expansion_service, tmp_governance_repo):
        scope = CapabilityScope(
            provider_id="native_alma",
            capability_id="console.stdout",
            behavior_profile=["write_stdout"],
        )
        entry = CapabilityMaturityEntry(
            scope=scope,
            maturity_state=CapabilityMaturityState.VERIFIED_BOUNDED,
            supported_behaviors=["write_stdout", "write_stderr"],
            unsupported_behaviors=[],
        )
        current = tmp_governance_repo.get_current_version()
        tmp_governance_repo.append_version(
            list(current.entries) + [entry],
            parent_version_id=current.version_id,
            change_summary="test verified_bounded stdout",
        )
        plan = expansion_service.generate_plan()
        stdout_missing = [
            c
            for c in plan.ranked_candidates
            if c.capability_id == "console.stdout" and c.behavior_id == "write_stdout"
        ]
        assert stdout_missing == []

    def test_06_verified_bounded_limitation_visible(self, expansion_service):
        _seed_open_existing_evidence(expansion_service)
        plan = expansion_service.generate_plan()
        cand = next(c for c in plan.ranked_candidates if c.behavior_id == "open_existing_readwrite")
        assert cand.limitations


class TestImpactLanguage:
    def test_07_blocker_removal_not_guaranteed(self, expansion_service):
        _seed_open_existing_evidence(expansion_service)
        plan = expansion_service.generate_plan()
        cand = next(c for c in plan.ranked_candidates if c.behavior_id == "open_existing_readwrite")
        summary = cand.impact.impact_summary.lower()
        assert "blocker" in summary or "identified" in summary
        assert "guaranteed compatibility" not in summary
        assert "will make" not in summary


class TestComplexityAndRisk:
    def test_08_complexity_deterministic(self):
        c1 = assess_complexity("filesystem.basic_io", "append_existing_file")
        c2 = assess_complexity("filesystem.basic_io", "append_existing_file")
        assert c1.level == c2.level
        assert c1.score == c2.score
        assert c1.factors == c2.factors

    def test_09_risk_factors_preserved(self, expansion_service):
        _seed_open_existing_evidence(expansion_service)
        plan = expansion_service.generate_plan()
        cand = next(c for c in plan.ranked_candidates if c.behavior_id == "open_existing_readwrite")
        assert cand.security_risk.categories
        assert cand.security_risk.explanations
        assert cand.semantic_risk.categories
        assert cand.semantic_risk.explanations


class TestHardExclusions:
    def test_10_hard_excluded_cannot_rank(self, expansion_service):
        plan = expansion_service.generate_plan()
        ranked_caps = {c.capability_id for c in plan.ranked_candidates}
        for cap in HARD_EXCLUDED_CAPABILITIES:
            assert cap not in ranked_caps

    def test_11_no_candidate_without_evidence(self, expansion_service):
        _seed_append_evidence(expansion_service)
        plan = expansion_service.generate_plan()
        for c in plan.ranked_candidates:
            assert c.evidence_references or c.observed_demand_count > 0


class TestCompositeScore:
    def test_12_composite_exposes_all_dimensions(self, expansion_service):
        _seed_append_evidence(expansion_service)
        plan = expansion_service.generate_plan()
        cand = plan.ranked_candidates[0]
        p = cand.priority
        assert p.demand_score is not None
        assert p.bounded_impact_score is not None
        assert p.engineering_cost_score is not None
        assert p.security_risk_score is not None
        assert p.semantic_risk_score is not None
        assert p.evidence_quality_score is not None
        assert p.testability_score is not None
        assert p.composite_score is not None


class TestUnknownApis:
    def test_13_unknown_apis_not_guessed(self, expansion_service):
        analysis = _append_analysis(
            binary_digest="unknown_bin",
            analysis_id="analysis_unknown",
            file_path="/unknown/app.exe",
        )
        analysis.api_classifications.append(
            ApiClassificationResult(
                dll="unknown.dll",
                function="UnknownExport",
                capability_id="api.unknown",
                complexity=ApiComplexity.MEDIUM,
                native_status=ImplementationStatus.UNKNOWN,
                wine_status=ImplementationStatus.UNKNOWN,
                is_known=False,
                provenance=_provenance(),
            )
        )
        expansion_service._analysis_repo.save(analysis)
        plan = expansion_service.generate_plan()
        unknown = [c for c in plan.ranked_candidates if c.capability_id == "api.unknown"]
        if unknown:
            assert unknown[0].capability_id == "api.unknown"
            assert "UnknownExport" in (unknown[0].behavior_id or "")


class TestRegistryImmutable:
    def test_14_registry_not_mutated(self, expansion_service, tmp_governance_repo):
        before = tmp_governance_repo.get_current_version()
        before_id = before.version_id
        before_digest = before.digest
        _seed_append_evidence(expansion_service)
        expansion_service.generate_plan()
        after = tmp_governance_repo.get_current_version()
        assert after.version_id == before_id
        assert after.digest == before_digest


class TestNoExecution:
    def test_15_no_execution_occurs(self, expansion_service):
        with patch("alma_bridge.compatibility_intelligence.service.analyze_pe") as mock_pe:
            _seed_append_evidence(expansion_service)
            expansion_service.generate_plan()
            mock_pe.assert_not_called()


class TestNoProviderChange:
    def test_16_no_provider_selection_change(self, expansion_service):
        with patch(
            "alma_bridge.compatibility_intelligence.prediction.CompatibilityPredictor.predict"
        ) as mock_predict:
            _seed_append_evidence(expansion_service)
            expansion_service.generate_plan()
            mock_predict.assert_not_called()


class TestRegistryVersionBinding:
    def test_17_old_analyses_retain_registry_version(self, expansion_service):
        _seed_append_evidence(expansion_service)
        records = expansion_service._calibration.list_records()
        assert records
        versions = {r.get("capability_registry_version") for r in records}
        assert all(v for v in versions)


class TestPlanDigest:
    def test_18_plan_digest_deterministic(self, expansion_service):
        _seed_append_evidence(expansion_service)
        p1 = expansion_service.generate_plan()
        p2 = expansion_service.generate_plan()
        assert p1.evidence_digest == p2.evidence_digest
        assert p1.plan_id == p2.plan_id


class TestFileAppendFixture:
    def test_19_file_append_unsupported_candidate(
        self, expansion_service, file_append_unsupported_path
    ):
        svc = CompatibilityIntelligenceService(
            repository=expansion_service._analysis_repo,
            calibration_repository=expansion_service._calibration_repo,
        )
        analysis = svc.analyze(str(file_append_unsupported_path), persist=True)
        assert analysis.binary_digest

        snap = build_prediction_snapshot(
            analysis,
            provider_id="native_alma",
            session_id="append_fixture_sess",
            fixture_name="file_append_unsupported.exe",
        )
        static = snap.static_coverage.model_copy(
            update={"behavior_gaps": ["append_existing_file"]}
        )
        snap = snap.model_copy(update={"static_coverage": static})
        expansion_service._calibration_repo.save_snapshot(snap)

        plan = expansion_service.generate_plan()
        append_candidates = [
            c for c in plan.ranked_candidates if c.behavior_id == "append_existing_file"
        ]
        assert append_candidates == [], "append_existing_file gap resolved — no expansion candidate"


class TestExplorerContract:
    def test_20_api_contract_distinct_dimensions(self, expansion_service):
        _seed_append_evidence(expansion_service)
        client = TestClient(app)
        resp = client.get("/bridge/compatibility/expansion/plan?provider_id=native_alma")
        assert resp.status_code == 200
        data = resp.json()
        assert "ranked_candidates" in data
        assert "limitations" in data
        if data["ranked_candidates"]:
            c = data["ranked_candidates"][0]
            assert "demand" in c
            assert "impact" in c
            assert "engineering_complexity" in c
            assert "security_risk" in c
            assert "semantic_risk" in c
            assert "evidence_references" in c
            assert "priority" in c
            assert c["priority"]["demand_score"] is not None


class TestDemandAggregatorUnit:
    def test_repeated_binary_dedup(self):
        agg = DemandAggregator()
        for i in range(3):
            agg.record_analysis(
                provider_id="native_alma",
                capability_id="filesystem.basic_io",
                behavior_id="append_existing_file",
                binary_digest="same",
                analysis_digest=f"a{i}",
                application_fingerprint="fp",
            )
        counts = agg.get_evidence("native_alma", "filesystem.basic_io", "append_existing_file")
        assert len(counts.binary_digests) == 1

    def test_hard_exclusion_no_fixture(self):
        reason = is_hard_excluded(
            "filesystem.basic_io",
            has_reproducible_fixture=False,
            implementation_scope="test scope",
        )
        assert reason is not None
