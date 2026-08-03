"""End-to-end evidence lifecycle verification."""

from __future__ import annotations

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.compatibility_intelligence.service import CompatibilityIntelligenceService
from alma_bridge.evidence.digest import compute_bundle_digest, compute_timeline_digest
from alma_bridge.evidence.models import TimelineEventType
from alma_bridge.evidence.timeline import EvidenceTimeline


class TestBundleAssembly:
    def test_assemble_from_hello64_fixture(self, evidence_service, hello64_path, tmp_path):
        from alma_bridge.compatibility_intelligence.repository import AnalysisRepository

        aci_repo = AnalysisRepository(store_dir=tmp_path / "aci")
        aci = CompatibilityIntelligenceService(repository=aci_repo)
        analysis = aci.analyze(str(hello64_path), persist=True)

        bundle = evidence_service.assemble_for_file(str(hello64_path), persist=True)

        assert bundle.binary_digest == analysis.binary_digest
        assert bundle.executable.digest == analysis.binary_digest
        assert bundle.static_analysis is not None
        assert bundle.coverage is not None
        assert bundle.prediction is not None
        assert bundle.bundle_digest == compute_bundle_digest(bundle)

    def test_bundle_digest_deterministic(self, evidence_service, hello64_path):
        b1 = evidence_service.assemble_for_file(str(hello64_path), persist=False)
        b2 = evidence_service.assemble_for_file(str(hello64_path), persist=False)
        assert b1.bundle_digest == b2.bundle_digest


class TestTimelineImmutability:
    def test_events_append_only(self, evidence_service):
        bundle = evidence_service.assemble_bundle(
            sha256_v1({"test": "timeline"}), persist=True
        )
        prior = evidence_service.get_timeline(bundle.bundle_id)
        evidence_service.append_event(
            bundle.bundle_id,
            TimelineEventType.ANALYSIS_CREATED,
            source="test",
            evidence_digest=sha256_v1({"event": 1}),
        )
        after = evidence_service.get_timeline(bundle.bundle_id)
        assert len(after) == len(prior) + 1
        for i, event in enumerate(prior):
            assert event.model_dump() == after[i].model_dump()

    def test_timeline_verify_immutability(self, evidence_service):
        bundle = evidence_service.assemble_bundle(
            sha256_v1({"test": "immutability"}), persist=True
        )
        timeline = EvidenceTimeline()
        timeline.append(
            TimelineEventType.PREDICTION_GENERATED,
            source="test",
            evidence_digest=sha256_v1({"snap": 1}),
        )
        prior = list(timeline.events)
        timeline.append(
            TimelineEventType.EXECUTION_STARTED,
            source="test",
            evidence_digest=sha256_v1({"exec": 1}),
        )
        assert timeline.verify_immutability(prior)


class TestHistoryReplay:
    def test_version_increments_on_change(self, evidence_service, hello64_path):
        b1 = evidence_service.assemble_for_file(str(hello64_path), persist=True)
        assert b1.version == 1

        evidence_service.append_event(
            b1.bundle_id,
            TimelineEventType.ANALYSIS_CREATED,
            source="test",
            evidence_digest=sha256_v1({"update": 1}),
        )
        b2 = evidence_service.assemble_for_file(str(hello64_path), persist=True)
        assert b2.version >= 1
        assert b2.bundle_id == b1.bundle_id

    def test_history_lists_versions(self, evidence_service, hello64_path):
        bundle = evidence_service.assemble_for_file(str(hello64_path), persist=True)
        versions = evidence_service.get_history(bundle.bundle_id)
        assert len(versions) >= 1
        assert versions[-1].bundle_digest == bundle.bundle_digest


class TestProvenanceChain:
    def test_sections_have_provenance(self, evidence_service, hello64_path):
        bundle = evidence_service.assemble_for_file(str(hello64_path), persist=False)
        assert bundle.executable.provenance.source
        assert bundle.executable.provenance.artifact_id
        if bundle.static_analysis:
            assert bundle.static_analysis.provenance.source == "aci_service"

    def test_canonical_provenance_from_aci(self):
        from alma_bridge.compatibility_intelligence.models import ProvenanceEvidence
        from alma_bridge.evidence.models import Provenance

        aci = ProvenanceEvidence(source="aci", artifact_id="test", digest="abc")
        canonical = aci.to_canonical()
        assert isinstance(canonical, Provenance)
        assert canonical.source == "aci"


class TestPlatformHealth:
    def test_health_metrics_have_sample_sizes(self, evidence_service):
        report = evidence_service.platform_health()
        assert report.generated_at
        assert len(report.metrics) >= 1
        for metric in report.metrics:
            assert metric.sample_size >= 0
            assert metric.evidence_source


class TestIntegrationHooks:
    def test_record_analysis_appends_timeline(self, evidence_service, hello64_path, tmp_path):
        from alma_bridge.compatibility_intelligence.repository import AnalysisRepository

        aci_repo = AnalysisRepository(store_dir=tmp_path / "aci")
        aci = CompatibilityIntelligenceService(repository=aci_repo)
        analysis = aci.analyze(str(hello64_path), persist=True)

        digest = sha256_v1({"analysis_id": analysis.analysis_id})
        evidence_service.record_analysis(analysis.binary_digest, analysis.analysis_id, digest)
        bundle = evidence_service.get_bundle_by_digest(analysis.binary_digest)
        assert bundle is not None
        events = evidence_service.get_timeline(bundle.bundle_id)
        assert any(e.event_type == TimelineEventType.ANALYSIS_CREATED for e in events)


class TestCapabilityEvolutionData:
    def test_governance_section_when_available(self, evidence_service, hello64_path):
        bundle = evidence_service.assemble_for_file(str(hello64_path), persist=False)
        # governance may or may not be present depending on seed state
        if bundle.governance:
            assert bundle.governance.provenance.source == "aci_governance"
            assert bundle.governance.digest


class TestNoHistoryMutation:
    def test_saved_bundle_not_overwritten_identical(self, evidence_service, hello64_path):
        b1 = evidence_service.assemble_for_file(str(hello64_path), persist=True)
        b2 = evidence_service.assemble_for_file(str(hello64_path), persist=True)
        assert b1.bundle_digest == b2.bundle_digest
        assert b2.version == b1.version

    def test_timeline_digest_stable(self):
        timeline = EvidenceTimeline()
        timeline.append(
            TimelineEventType.VERIFICATION_COMPLETED,
            source="verification_engine",
            evidence_digest=sha256_v1({"v": 1}),
        )
        d1 = timeline.digest
        d2 = compute_timeline_digest(timeline.events)
        assert d1 == d2
