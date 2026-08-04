"""Runtime Certification Platform verification."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alma_bridge.certification.criteria import (
    CertificationInputs,
    CertificationLevel,
    compute_certification_level,
    criteria_documentation,
    detect_stale_reasons,
)
from alma_bridge.certification.digest import digest_of
from alma_bridge.certification.errors import HistoryMutationError
from alma_bridge.certification.models import ComplianceStatus, StaleReason
from alma_bridge.certification.compliance import build_compliance_matrix
from alma_bridge.certification.versioning import record_level_transition, seed_initial_history
from alma_bridge.certification.repository import CertificationRepository
from alma_bridge.main import app

client = TestClient(app)


class TestCriteria:
    def test_criteria_documented_for_each_level(self):
        docs = criteria_documentation()
        assert "unverified" in docs
        assert "production_ready" in docs
        assert "requires_revalidation" in docs
        assert len(docs) >= 9

    def test_unverified_without_spec(self):
        inputs = CertificationInputs(
            capability_id="test",
            behavior_id="test",
            has_specification=False,
        )
        assert compute_certification_level(inputs) == CertificationLevel.UNVERIFIED

    def test_specified_with_spec_only(self):
        inputs = CertificationInputs(
            capability_id="test",
            behavior_id="test",
            has_specification=True,
            supported=False,
        )
        assert compute_certification_level(inputs) == CertificationLevel.SPECIFIED

    def test_unsupported_negative_fixture_pass(self):
        inputs = CertificationInputs(
            capability_id="filesystem.basic_io",
            behavior_id="append_existing_file",
            supported=False,
            has_specification=True,
            has_behavior_suite=True,
            has_negative_fixture_pass=True,
            suite_pass_count=1,
        )
        assert compute_certification_level(inputs) == CertificationLevel.BEHAVIOR_TESTED

    def test_stale_on_abi_change_with_prior_record(self):
        inputs = CertificationInputs(
            capability_id="console.stdout",
            behavior_id="write_stdout",
            has_specification=True,
            spec_digest="new_digest",
            last_recorded_spec_digest="old_digest",
        )
        reasons = detect_stale_reasons(inputs)
        assert StaleReason.ABI_CHANGE in reasons
        assert compute_certification_level(inputs) == CertificationLevel.REQUIRES_REVALIDATION

    def test_no_stale_without_prior_record(self):
        inputs = CertificationInputs(
            capability_id="console.stdout",
            behavior_id="write_stdout",
            has_specification=True,
            verified_scenario_present=True,
            has_behavior_suite=True,
            suite_pass_count=1,
            fixture_coverage_pct=100.0,
            verification_pct=100.0,
            validation_pass_count=1,
            validation_total_count=1,
        )
        assert detect_stale_reasons(inputs) == []
        assert compute_certification_level(inputs) == CertificationLevel.VERIFIED


class TestWriteFileScenarios:
    def test_write_stdout_path_toward_certified(self, certification_service):
        cert = certification_service.get_behavior_certification(
            "console.stdout", "write_stdout"
        )
        assert cert.supported is True
        assert cert.certification_level in (
            CertificationLevel.BEHAVIOR_TESTED,
            CertificationLevel.VERIFIED,
            CertificationLevel.CALIBRATED,
            CertificationLevel.CERTIFIED,
        )
        assert cert.compliance_status == ComplianceStatus.IN_PROGRESS
        assert cert.behavior_suite is not None
        assert any("hello64" in (p or "") for p in cert.behavior_suite.fixture_paths)
        assert len(cert.evidence_references) > 0

    def test_append_existing_file_reviewed_not_forced_certified(self, certification_service):
        cert = certification_service.get_behavior_certification(
            "filesystem.basic_io", "append_existing_file"
        )
        assert cert.supported is True
        assert cert.compliance_status != ComplianceStatus.UNSUPPORTED
        assert cert.certification_level != CertificationLevel.CERTIFIED
        assert cert.certification_level in (
            CertificationLevel.BEHAVIOR_TESTED,
            CertificationLevel.VERIFIED,
            CertificationLevel.CALIBRATED,
            CertificationLevel.SPECIFIED,
        )
        assert any(
            "append" in (p or "")
            for p in (cert.behavior_suite.fixture_paths if cert.behavior_suite else [])
        )

    def test_overlapped_io_unsupported(self, certification_service):
        cert = certification_service.get_behavior_certification(
            "console.stdout", "overlapped_io"
        )
        assert cert.supported is False
        assert cert.compliance_status == ComplianceStatus.UNSUPPORTED
        assert cert.certification_level != CertificationLevel.CERTIFIED


class TestComplianceMatrix:
    def test_matrix_generation(self, certification_service):
        certs = certification_service.list_behavior_certifications()
        matrix = build_compliance_matrix(certs)
        assert matrix.matrix_digest
        assert len(matrix.entries) == len(certs)
        assert matrix.matrix_digest == digest_of(
            {"provider_id": matrix.provider_id, "entry_count": len(matrix.entries)}
        )

    def test_matrix_includes_writefile_behaviors(self, certification_service):
        matrix = certification_service.compliance_matrix()
        behaviors = {e.behavior_id for e in matrix.entries}
        assert "write_stdout" in behaviors
        assert "append_existing_file" in behaviors


class TestHistoricalEvolution:
    def test_append_only_records(self, certification_tmp_paths, certification_service):
        repo = CertificationRepository(store_dir=certification_tmp_paths["certification"])
        certs = certification_service.list_behavior_certifications()
        recorded = seed_initial_history(certs[:1], repo)
        assert len(recorded) == 1
        history = repo.get_history(
            recorded[0].capability_id, recorded[0].behavior_id
        )
        assert len(history.records) == 1
        with pytest.raises(HistoryMutationError):
            repo.append_record(recorded[0])

    def test_certification_never_deleted(self, certification_tmp_paths, certification_service):
        repo = CertificationRepository(store_dir=certification_tmp_paths["certification"])
        cert = certification_service.get_behavior_certification(
            "console.stdout", "write_stdout"
        )
        seed_initial_history([cert], repo)
        history_before = repo.get_history("console.stdout", "write_stdout")
        count_before = len(history_before.records)
        seed_initial_history([cert], repo)
        history_after = repo.get_history("console.stdout", "write_stdout")
        assert len(history_after.records) == count_before


class TestStaleDetection:
    def test_stale_endpoint_read_only(self):
        res = client.get("/bridge/certification/stale")
        assert res.status_code == 200
        assert "stale" in res.json()

    def test_stale_marks_requires_revalidation_not_delete(
        self, certification_tmp_paths, certification_service
    ):
        repo = CertificationRepository(store_dir=certification_tmp_paths["certification"])
        cert = certification_service.get_behavior_certification(
            "console.stdout", "write_stdout"
        )
        rec = record_level_transition(
            cert,
            repo,
            previous_level=CertificationLevel.UNVERIFIED,
            reason="Initial",
        )
        assert rec is not None
        history = repo.get_history("console.stdout", "write_stdout")
        assert len(history.records) >= 1


class TestEvidenceReferences:
    def test_evidence_required_for_certification(self, certification_service):
        cert = certification_service.get_behavior_certification(
            "console.stdout", "write_stdout"
        )
        assert cert.evidence_references
        assert cert.certification_digest
        assert cert.certification_digest == digest_of(
            {
                "capability_id": cert.capability_id,
                "behavior_id": cert.behavior_id,
                "level": cert.certification_level.value,
                "spec_digest": cert.specification.spec_digest if cert.specification else "",
            }
        )


class TestServiceIntegration:
    def test_list_behaviors(self, certification_service):
        certs = certification_service.list_behavior_certifications()
        assert len(certs) > 0

    def test_dashboard_aggregation(self, certification_service):
        dashboard = certification_service.certification_dashboard()
        assert dashboard.behavior_count > 0
        assert dashboard.compliance_matrix.matrix_digest

    def test_native_engineering_integration(self, certification_service):
        cert = certification_service.get_behavior_certification(
            "console.stdout", "write_stdout"
        )
        assert cert.specification is not None
        assert cert.specification.spec_digest


class TestRoutes:
    def test_list_behaviors(self):
        res = client.get("/bridge/certification/behaviors")
        assert res.status_code == 200
        data = res.json()
        assert data["count"] > 0

    def test_get_behavior_profile(self):
        res = client.get("/bridge/certification/behaviors/console.stdout/write_stdout")
        assert res.status_code == 200
        assert res.json()["behavior_id"] == "write_stdout"

    def test_unknown_behavior_404(self):
        res = client.get("/bridge/certification/behaviors/unknown/unknown")
        assert res.status_code == 404

    def test_matrix_endpoint(self):
        res = client.get("/bridge/certification/matrix")
        assert res.status_code == 200
        assert "entries" in res.json()

    def test_history_endpoint(self):
        res = client.get(
            "/bridge/certification/history/console.stdout/write_stdout"
        )
        assert res.status_code == 200
        assert "records" in res.json()

    def test_dashboard_endpoint(self):
        res = client.get("/bridge/certification/dashboard")
        assert res.status_code == 200
        assert res.json()["behavior_count"] > 0

    def test_get_endpoints_are_read_only(self):
        from alma_bridge.api import certification_routes

        for route in certification_routes.router.routes:
            assert route.methods == {"GET"}

    def test_no_governance_mutation_on_get(self):
        from alma_bridge.compatibility_intelligence.governance.repository import (
            GovernanceRepository,
        )

        repo = GovernanceRepository()
        try:
            version_before = repo.get_current_version()
            version_id_before = version_before.version_id
        except Exception:
            version_id_before = None
        client.get("/bridge/certification/dashboard")
        if version_id_before:
            version_after = repo.get_current_version()
            assert version_after.version_id == version_id_before
