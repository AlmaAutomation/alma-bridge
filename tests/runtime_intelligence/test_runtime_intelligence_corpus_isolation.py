"""Regression tests for Runtime Intelligence corpus isolation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from alma_bridge.runtime_intelligence.history import RuntimeIntelligenceHistory
from alma_bridge.runtime_intelligence.index import compute_compatibility_index
from alma_bridge.runtime_intelligence.knowledge import compute_knowledge_coverage
from alma_bridge.runtime_intelligence.models import (
    BehaviorFamilyId,
    CompatibilityIndexStatus,
    CorpusKind,
    KnowledgeCoverageStatus,
    RuntimeIntelligenceMetricId,
)
from alma_bridge.runtime_intelligence.queries import RuntimeIntelligenceQueries
from alma_bridge.runtime_intelligence.service import RuntimeIntelligenceService


def _queries_with_calibration(records: list) -> RuntimeIntelligenceQueries:
    return RuntimeIntelligenceQueries(
        corpus_resolver=__import__(
            "alma_bridge.runtime_intelligence.corpus", fromlist=["CorpusEnrollmentResolver"]
        ).CorpusEnrollmentResolver.from_manifest_files(),
        evidence_queries=MagicMock(list_bundle_ids=MagicMock(return_value=[]), timeline=MagicMock(return_value=[])),
        analysis_repo=MagicMock(list_recent=MagicMock(return_value=[])),
        calibration_service=MagicMock(list_records=MagicMock(return_value=records)),
        governance_repo=MagicMock(get_current_version=MagicMock(side_effect=RuntimeError("no gov"))),
        certification_service=MagicMock(
            get_behavior_certification=MagicMock(side_effect=RuntimeError("no cert"))
        ),
        expansion_repo=MagicMock(get_latest_plan=MagicMock(side_effect=RuntimeError("no plan"))),
    )


def _service(queries: RuntimeIntelligenceQueries) -> RuntimeIntelligenceService:
    return RuntimeIntelligenceService(
        queries=queries,
        evidence_repo=MagicMock(),
        evidence_queries=MagicMock(list_bundle_ids=MagicMock(return_value=[]), timeline=MagicMock(return_value=[])),
    )


class TestCorpusIsolationRegression:
    def test_evidence_snapshot_digest_differs_by_corpus(self, corpus_resolver):
        queries = RuntimeIntelligenceQueries(corpus_resolver=corpus_resolver)
        eng = queries.compute_evidence_snapshot_digest(
            CorpusKind.ENGINEERING,
            family_id=BehaviorFamilyId.FILESYSTEM,
            provider_id="native_alma",
        )
        rw = queries.compute_evidence_snapshot_digest(
            CorpusKind.REAL_WORLD,
            family_id=BehaviorFamilyId.FILESYSTEM,
            provider_id="native_alma",
        )
        assert eng != rw

    def test_real_world_index_is_insufficient_without_enrollment(self, corpus_resolver):
        queries = RuntimeIntelligenceQueries(
            corpus_resolver=corpus_resolver,
            evidence_queries=MagicMock(list_bundle_ids=MagicMock(return_value=[]), timeline=MagicMock(return_value=[])),
            analysis_repo=MagicMock(list_recent=MagicMock(return_value=[])),
            calibration_service=MagicMock(list_records=MagicMock(return_value=[])),
            governance_repo=MagicMock(get_current_version=MagicMock(side_effect=RuntimeError("no gov"))),
            certification_service=MagicMock(
                get_behavior_certification=MagicMock(side_effect=RuntimeError("no cert"))
            ),
            expansion_repo=MagicMock(get_latest_plan=MagicMock(side_effect=RuntimeError("no plan"))),
        )
        digest = queries.compute_evidence_snapshot_digest(
            CorpusKind.REAL_WORLD,
            family_id=BehaviorFamilyId.FILESYSTEM,
            provider_id="native_alma",
        )
        input_data, meta = queries.build_index_input(
            CorpusKind.REAL_WORLD,
            BehaviorFamilyId.FILESYSTEM,
            "native_alma",
            digest,
        )
        report = compute_compatibility_index(input_data)
        assert report.status == CompatibilityIndexStatus.INSUFFICIENT_EVIDENCE
        assert report.index_value is None
        assert "no_enrolled_corpus_artifacts" in meta.limitations

    def test_real_world_knowledge_is_insufficient_without_enrollment(self, corpus_resolver):
        queries = RuntimeIntelligenceQueries(
            corpus_resolver=corpus_resolver,
            evidence_queries=MagicMock(list_bundle_ids=MagicMock(return_value=[]), timeline=MagicMock(return_value=[])),
            analysis_repo=MagicMock(list_recent=MagicMock(return_value=[])),
            calibration_service=MagicMock(list_records=MagicMock(return_value=[])),
            governance_repo=MagicMock(get_current_version=MagicMock(side_effect=RuntimeError("no gov"))),
            certification_service=MagicMock(),
            expansion_repo=MagicMock(get_latest_plan=MagicMock(side_effect=RuntimeError("no plan"))),
        )
        digest = "snap-rw-empty"
        input_data, meta = queries.build_knowledge_input(
            CorpusKind.REAL_WORLD,
            BehaviorFamilyId.FILESYSTEM,
            "native_alma",
            digest,
        )
        report = compute_knowledge_coverage(input_data)
        assert report.status == KnowledgeCoverageStatus.INSUFFICIENT_EVIDENCE
        assert report.knowledge_coverage_value is None
        assert "no_enrolled_corpus_artifacts" in meta.limitations

    def test_real_world_debt_empty_without_enrollment(self, corpus_resolver):
        queries = RuntimeIntelligenceQueries(
            corpus_resolver=corpus_resolver,
            evidence_queries=MagicMock(),
            analysis_repo=MagicMock(list_recent=MagicMock(return_value=[])),
            calibration_service=MagicMock(list_records=MagicMock(return_value=[])),
            expansion_repo=MagicMock(get_latest_plan=MagicMock(side_effect=RuntimeError("no plan"))),
        )
        signals, meta = queries.build_debt_signals(
            CorpusKind.REAL_WORLD,
            BehaviorFamilyId.FILESYSTEM,
            "native_alma",
            "snap-rw-debt",
        )
        assert signals == []
        assert "no_enrolled_corpus_artifacts" in meta.limitations

    def test_engineering_calibration_does_not_affect_real_world(
        self,
        engineering_hello64_digest,
        engineering_hello64_fingerprint,
    ):
        calibration_records = [
            {
                "provider_id": "native_alma",
                "capability_id": "filesystem.basic_io",
                "classification": "true_positive",
                "application_fingerprint": engineering_hello64_fingerprint,
                "binary_digest": engineering_hello64_digest,
                "record_id": "cal-eng-only",
                "outcome_link_id": "link-1",
                "failure_attribution": "runtime",
            }
        ]
        queries = _queries_with_calibration(calibration_records)
        eng_digest = queries.compute_evidence_snapshot_digest(
            CorpusKind.ENGINEERING,
            family_id=BehaviorFamilyId.FILESYSTEM,
            provider_id="native_alma",
        )
        rw_digest = queries.compute_evidence_snapshot_digest(
            CorpusKind.REAL_WORLD,
            family_id=BehaviorFamilyId.FILESYSTEM,
            provider_id="native_alma",
        )
        eng_input, _ = queries.build_knowledge_input(
            CorpusKind.ENGINEERING,
            BehaviorFamilyId.FILESYSTEM,
            "native_alma",
            eng_digest,
        )
        rw_input, rw_meta = queries.build_knowledge_input(
            CorpusKind.REAL_WORLD,
            BehaviorFamilyId.FILESYSTEM,
            "native_alma",
            rw_digest,
        )
        eng_report = compute_knowledge_coverage(eng_input)
        rw_report = compute_knowledge_coverage(rw_input)
        assert eng_report.knowledge_coverage_value is not None or eng_report.status.value == "insufficient_evidence"
        assert rw_report.status == KnowledgeCoverageStatus.INSUFFICIENT_EVIDENCE
        assert rw_report.knowledge_coverage_value is None
        assert "no_enrolled_corpus_artifacts" in rw_meta.limitations

    def test_service_reports_differ_between_corpora(self, corpus_resolver):
        service = _service(_queries_with_calibration([]))
        eng = service.get_report(CorpusKind.ENGINEERING)
        rw = service.get_report(CorpusKind.REAL_WORLD)
        assert eng.evidence_snapshot_digest != rw.evidence_snapshot_digest
        assert eng.report_digest != rw.report_digest
        for idx in rw.compatibility_indexes:
            assert idx.status == CompatibilityIndexStatus.INSUFFICIENT_EVIDENCE
            assert idx.index_value is None
        for kn in rw.knowledge_coverage:
            assert kn.status == KnowledgeCoverageStatus.INSUFFICIENT_EVIDENCE
            assert kn.knowledge_coverage_value is None

    def test_hypothesis_without_corpus_metadata_not_defaulted_to_engineering(self, corpus_resolver):
        from alma_bridge.evidence.models import Provenance, TimelineEvent, TimelineEventType

        event = TimelineEvent(
            event_id="evt-no-corpus",
            event_type=TimelineEventType.ENGINEERING_HYPOTHESIS_CREATED,
            timestamp="2026-01-01T00:00:00+00:00",
            version=1,
            evidence_digest="dig",
            source="runtime_intelligence",
            references=["hyp-1"],
            provenance=Provenance(source="runtime_intelligence", artifact_id="hyp-1", digest="dig"),
            metadata={
                "hypothesis_id": "hyp-no-corpus",
                "created_at": "2026-01-01T00:00:00+00:00",
                "provider_id": "native_alma",
                "provider_version_scope": "0.1",
                "family_id": "filesystem",
                "capability_id": "filesystem.basic_io",
                "bounded_scope": "test",
                "evidence_snapshot_digest": "snap",
                "snapshot_digest": "snap",
                "schema_version": "v1",
                "formula_version": "v1",
            },
        )
        evidence = MagicMock(
            list_bundle_ids=MagicMock(return_value=["bundle-1"]),
            timeline=MagicMock(return_value=[event]),
        )
        queries = RuntimeIntelligenceQueries(
            corpus_resolver=corpus_resolver,
            evidence_queries=evidence,
        )
        eng_snapshots, _ = queries.list_hypothesis_timeline_events(CorpusKind.ENGINEERING)
        rw_snapshots, _ = queries.list_hypothesis_timeline_events(CorpusKind.REAL_WORLD)
        assert eng_snapshots == []
        assert rw_snapshots == []

    def test_engineering_hypothesis_not_visible_in_real_world(self, corpus_resolver):
        from alma_bridge.evidence.models import Provenance, TimelineEvent, TimelineEventType

        event = TimelineEvent(
            event_id="evt-eng-hyp",
            event_type=TimelineEventType.ENGINEERING_HYPOTHESIS_CREATED,
            timestamp="2026-01-01T00:00:00+00:00",
            version=1,
            evidence_digest="dig",
            source="runtime_intelligence",
            references=["hyp-eng"],
            provenance=Provenance(source="runtime_intelligence", artifact_id="hyp-eng", digest="dig"),
            metadata={
                "hypothesis_id": "hyp-eng",
                "created_at": "2026-01-01T00:00:00+00:00",
                "corpus": "engineering",
                "provider_id": "native_alma",
                "provider_version_scope": "0.1",
                "family_id": "filesystem",
                "capability_id": "filesystem.basic_io",
                "bounded_scope": "test",
                "evidence_snapshot_digest": "snap",
                "snapshot_digest": "snap",
                "schema_version": "v1",
                "formula_version": "v1",
            },
        )
        evidence = MagicMock(
            list_bundle_ids=MagicMock(return_value=["bundle-1"]),
            timeline=MagicMock(return_value=[event]),
        )
        queries = RuntimeIntelligenceQueries(
            corpus_resolver=corpus_resolver,
            evidence_queries=evidence,
        )
        eng_snapshots, _ = queries.list_hypothesis_timeline_events(CorpusKind.ENGINEERING)
        rw_snapshots, _ = queries.list_hypothesis_timeline_events(CorpusKind.REAL_WORLD)
        assert len(eng_snapshots) == 1
        assert eng_snapshots[0].hypothesis_id == "hyp-eng"
        assert rw_snapshots == []

    def test_index_digests_differ_between_corpora_with_same_scope(self, corpus_resolver):
        queries = RuntimeIntelligenceQueries(
            corpus_resolver=corpus_resolver,
            evidence_queries=MagicMock(list_bundle_ids=MagicMock(return_value=[]), timeline=MagicMock(return_value=[])),
            analysis_repo=MagicMock(list_recent=MagicMock(return_value=[])),
            calibration_service=MagicMock(list_records=MagicMock(return_value=[])),
            governance_repo=MagicMock(get_current_version=MagicMock(side_effect=RuntimeError("no gov"))),
            certification_service=MagicMock(
                get_behavior_certification=MagicMock(side_effect=RuntimeError("no cert"))
            ),
            expansion_repo=MagicMock(get_latest_plan=MagicMock(side_effect=RuntimeError("no plan"))),
        )
        service = RuntimeIntelligenceService(queries=queries)
        eng = service.get_index(CorpusKind.ENGINEERING, BehaviorFamilyId.FILESYSTEM, "native_alma")
        rw = service.get_index(CorpusKind.REAL_WORLD, BehaviorFamilyId.FILESYSTEM, "native_alma")
        assert eng.report_digest != rw.report_digest
        assert rw.status == CompatibilityIndexStatus.INSUFFICIENT_EVIDENCE

    def test_verification_history_empty_for_unenrolled_corpus(self, corpus_resolver, real_world_corpus):
        history = RuntimeIntelligenceHistory(
            RuntimeIntelligenceQueries(
                corpus_resolver=corpus_resolver,
                evidence_queries=MagicMock(list_bundle_ids=MagicMock(return_value=[])),
            )
        )
        report = history.build_history_report(
            real_world_corpus,
            RuntimeIntelligenceMetricId.VERIFICATION_RATE.value,
        )
        assert report.points == []
        assert "insufficient_timeline_evidence_for_metric" in report.limitations
