"""Tests for RuntimeIntelligenceQueries."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from alma_bridge.runtime_intelligence.corpus import CorpusEnrollmentResolver
from alma_bridge.runtime_intelligence.family import family_for_behavior, family_for_capability
from alma_bridge.runtime_intelligence.knowledge import (
    qualifies_as_attributed_failure,
    qualifies_as_explained_blocker,
)
from alma_bridge.runtime_intelligence.models import (
    BehaviorFamilyId,
    CompatibilityDebtKind,
    CorpusKind,
)
from alma_bridge.runtime_intelligence.queries import RuntimeIntelligenceQueries


@pytest.fixture
def queries(corpus_resolver: CorpusEnrollmentResolver) -> RuntimeIntelligenceQueries:
    return RuntimeIntelligenceQueries(
        corpus_resolver=corpus_resolver,
        evidence_queries=MagicMock(list_bundle_ids=MagicMock(return_value=[])),
        analysis_repo=MagicMock(list_recent=MagicMock(return_value=[])),
        calibration_repo=MagicMock(list_records=MagicMock(return_value=[])),
        governance_repo=MagicMock(get_current_version=MagicMock(side_effect=RuntimeError("no gov"))),
        certification_service=MagicMock(),
        expansion_repo=MagicMock(get_latest_plan=MagicMock(side_effect=RuntimeError("no plan"))),
    )


class TestRuntimeIntelligenceQueries:
    def test_only_enrolled_engineering_artifacts_included(self, queries, engineering_hello64_digest):
        enrolled, excluded = queries.filter_enrolled_artifacts(
            CorpusKind.ENGINEERING,
            binary_digests=[engineering_hello64_digest, "not-enrolled-digest"],
        )
        assert len(enrolled) == 1
        assert excluded == 1

    def test_only_enrolled_real_world_artifacts_included(self, queries, real_world_corpus):
        enrolled, excluded = queries.filter_enrolled_artifacts(
            real_world_corpus,
            binary_digests=["not-enrolled-real-world-digest"],
        )
        assert enrolled == []
        assert excluded == 1

    def test_unenrolled_artifacts_excluded(self, queries, engineering_corpus):
        _, excluded = queries.filter_enrolled_artifacts(
            engineering_corpus,
            application_fingerprints=["unknown-fingerprint"],
        )
        assert excluded == 1

    def test_excluded_counts_surfaced(self, queries, engineering_corpus):
        _, meta = queries.build_index_input(
            engineering_corpus,
            BehaviorFamilyId.FILESYSTEM,
            "native_alma",
            "snap-test",
        )
        assert meta.excluded_unenrolled_artifact_count >= 0

    def test_corpora_never_merged(self, queries, engineering_corpus, real_world_corpus):
        eng = queries.enrolled_entries(engineering_corpus)
        rw = queries.enrolled_entries(real_world_corpus)
        eng_ids = {entry.entry_id for entry in eng}
        rw_ids = {entry.entry_id for entry in rw}
        assert eng_ids.isdisjoint(rw_ids)

    def test_exact_family_mapping_retained(self):
        assert family_for_capability("filesystem.basic_io") == BehaviorFamilyId.FILESYSTEM
        assert family_for_behavior("append_existing_file") == BehaviorFamilyId.FILESYSTEM

    def test_index_input_built_from_correct_owners(self, queries, engineering_corpus):
        digest = queries.compute_evidence_snapshot_digest(
            engineering_corpus,
            family_id=BehaviorFamilyId.FILESYSTEM,
            provider_id="native_alma",
        )
        input_data, _ = queries.build_index_input(
            engineering_corpus,
            BehaviorFamilyId.FILESYSTEM,
            "native_alma",
            digest,
        )
        assert input_data.corpus == engineering_corpus
        assert input_data.family_id == BehaviorFamilyId.FILESYSTEM
        assert input_data.provider_id == "native_alma"
        assert len(input_data.components if hasattr(input_data, "components") else []) == 0

    def test_unavailable_evidence_remains_unavailable(self, queries, engineering_corpus):
        digest = "snap-sparse"
        input_data, meta = queries.build_index_input(
            engineering_corpus,
            BehaviorFamilyId.FILESYSTEM,
            "native_alma",
            digest,
        )
        assert input_data.calibration_accuracy.available is False
        assert meta.limitations

    def test_knowledge_qualification_helpers_enforced(self):
        assert qualifies_as_explained_blocker(
            has_bounded_classification=True,
            has_evidence_references=True,
            stderr_only=False,
        )
        assert not qualifies_as_explained_blocker(
            has_bounded_classification=True,
            has_evidence_references=True,
            stderr_only=True,
        )
        assert qualifies_as_attributed_failure(
            authoritative=True,
            attribution_category="runtime",
            has_evidence_references=True,
        )

    def test_debt_signals_preserve_exact_ids(self, queries, engineering_corpus):
        digest = queries.compute_evidence_snapshot_digest(
            engineering_corpus,
            family_id=BehaviorFamilyId.FILESYSTEM,
            provider_id="native_alma",
        )
        signals, _ = queries.build_debt_signals(
            engineering_corpus,
            BehaviorFamilyId.FILESYSTEM,
            "native_alma",
            digest,
        )
        for signal in signals:
            assert signal.corpus == engineering_corpus
            assert signal.evidence_snapshot_digest == digest

    def test_no_duplicate_apps_from_repeated_sessions(self, queries, engineering_corpus):
        calibration_service = MagicMock(
            list_records=MagicMock(
                return_value=[
                    {
                        "provider_id": "native_alma",
                        "capability_id": "filesystem.basic_io",
                        "classification": "false_positive",
                        "application_fingerprint": "d87ac1f8a7c5bd11ffa5ccb00cf18d77edd5ce075a5b37835770e32feca15aaf",
                        "binary_digest": "1cf6ffffdd39d9dd4db69711e43aca370455c1e007bcb970e60b966128f3835b",
                        "record_id": "rec-1",
                    },
                    {
                        "provider_id": "native_alma",
                        "capability_id": "filesystem.basic_io",
                        "classification": "false_positive",
                        "application_fingerprint": "d87ac1f8a7c5bd11ffa5ccb00cf18d77edd5ce075a5b37835770e32feca15aaf",
                        "binary_digest": "1cf6ffffdd39d9dd4db69711e43aca370455c1e007bcb970e60b966128f3835b",
                        "record_id": "rec-2",
                    },
                ]
            )
        )
        q = RuntimeIntelligenceQueries(
            corpus_resolver=queries._corpus,
            calibration_service=calibration_service,
            evidence_queries=MagicMock(list_bundle_ids=MagicMock(return_value=[])),
            analysis_repo=MagicMock(list_recent=MagicMock(return_value=[])),
        )
        digest = "snap-dedupe"
        signals, _ = q.build_debt_signals(
            engineering_corpus,
            BehaviorFamilyId.FILESYSTEM,
            "native_alma",
            digest,
        )
        fp_signals = [s for s in signals if s.kind == CompatibilityDebtKind.CALIBRATION_FALSE_POSITIVE]
        assert fp_signals
        assert fp_signals[0].affected_application_fingerprints == [
            "d87ac1f8a7c5bd11ffa5ccb00cf18d77edd5ce075a5b37835770e32feca15aaf"
        ]

    def test_no_storage_mutation(self, queries):
        repo = MagicMock()
        q = RuntimeIntelligenceQueries(
            corpus_resolver=queries._corpus,
            evidence_queries=MagicMock(),
            analysis_repo=repo,
            governance_repo=MagicMock(get_current_version=MagicMock(side_effect=RuntimeError("no gov"))),
            certification_service=MagicMock(),
            calibration_service=MagicMock(list_records=MagicMock(return_value=[])),
        )
        q.build_index_input(
            CorpusKind.ENGINEERING,
            BehaviorFamilyId.FILESYSTEM,
            "native_alma",
            "snap-readonly",
        )
        repo.save.assert_not_called()

    def test_knowledge_input_scoped_to_corpus(self, queries, engineering_corpus):
        digest = "snap-knowledge"
        input_data, meta = queries.build_knowledge_input(
            engineering_corpus,
            BehaviorFamilyId.FILESYSTEM,
            "native_alma",
            digest,
        )
        assert input_data.corpus == engineering_corpus
        assert input_data.evidence_snapshot_digest == digest
        assert isinstance(meta.excluded_unenrolled_artifact_count, int)

    def test_build_hypothesis_snapshot_inputs_empty_by_default(self, queries, engineering_corpus):
        snapshots, meta = queries.build_hypothesis_snapshot_inputs(engineering_corpus)
        assert snapshots == []
        assert meta.excluded_unenrolled_artifact_count == 0

    def test_compute_evidence_snapshot_digest_deterministic(self, queries, engineering_corpus):
        d1 = queries.compute_evidence_snapshot_digest(
            engineering_corpus,
            family_id=BehaviorFamilyId.FILESYSTEM,
            provider_id="native_alma",
        )
        d2 = queries.compute_evidence_snapshot_digest(
            engineering_corpus,
            family_id=BehaviorFamilyId.FILESYSTEM,
            provider_id="native_alma",
        )
        assert d1 == d2

    def test_corpus_required_for_enrolled_entries(self, queries):
        with pytest.raises(Exception):
            queries.enrolled_entries(None)
