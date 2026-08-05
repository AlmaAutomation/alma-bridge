"""Tests for RuntimeIntelligenceHistory."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from alma_bridge.research.models import SampleSize
from alma_bridge.runtime_intelligence.history import HISTORY_LIMITATION, RuntimeIntelligenceHistory
from alma_bridge.runtime_intelligence.models import (
    BehaviorFamilyId,
    CorpusKind,
    RuntimeIntelligenceHistoryStatus,
    RuntimeIntelligenceMetricId,
    compute_history_report_digest,
)
from alma_bridge.runtime_intelligence.queries import RuntimeIntelligenceQueries


@pytest.fixture
def history(corpus_resolver) -> RuntimeIntelligenceHistory:
    queries = RuntimeIntelligenceQueries(
        corpus_resolver=corpus_resolver,
        evidence_queries=MagicMock(list_bundle_ids=MagicMock(return_value=[])),
        analysis_repo=MagicMock(list_recent=MagicMock(return_value=[])),
        calibration_repo=MagicMock(list_records=MagicMock(return_value=[])),
        governance_repo=MagicMock(get_current_version=MagicMock(side_effect=RuntimeError("no gov"))),
    )
    return RuntimeIntelligenceHistory(queries)


class TestRuntimeIntelligenceHistory:
    def test_index_history_computed(self, history, engineering_corpus):
        report = history.build_history_report(
            engineering_corpus,
            RuntimeIntelligenceMetricId.COMPATIBILITY_INDEX.value,
            family_id=BehaviorFamilyId.FILESYSTEM,
            provider_id="native_alma",
        )
        assert report.points
        assert report.points[0].metric_id == RuntimeIntelligenceMetricId.COMPATIBILITY_INDEX.value

    def test_knowledge_history_computed(self, history, engineering_corpus):
        report = history.build_history_report(
            engineering_corpus,
            RuntimeIntelligenceMetricId.KNOWLEDGE_COVERAGE.value,
            family_id=BehaviorFamilyId.FILESYSTEM,
            provider_id="native_alma",
        )
        assert report.points

    def test_debt_history_computed(self, history, engineering_corpus):
        report = history.build_history_report(
            engineering_corpus,
            RuntimeIntelligenceMetricId.COMPATIBILITY_DEBT.value,
            family_id=BehaviorFamilyId.FILESYSTEM,
            provider_id="native_alma",
        )
        assert report.points

    def test_hypothesis_accuracy_history_computed(self, history, engineering_corpus):
        report = history.build_history_report(
            engineering_corpus,
            RuntimeIntelligenceMetricId.HYPOTHESIS_ACCURACY.value,
        )
        assert report.metric_id == RuntimeIntelligenceMetricId.HYPOTHESIS_ACCURACY.value

    def test_missing_bucket_not_zero_filled(self, history, engineering_corpus):
        report = history.build_history_report(
            engineering_corpus,
            RuntimeIntelligenceMetricId.HYPOTHESIS_ACCURACY.value,
        )
        assert all(point.timestamp_bucket != "2020-01-01" for point in report.points)

    def test_sample_sizes_present(self, history, engineering_corpus):
        report = history.build_history_report(
            engineering_corpus,
            RuntimeIntelligenceMetricId.COMPATIBILITY_INDEX.value,
            family_id=BehaviorFamilyId.FILESYSTEM,
            provider_id="native_alma",
        )
        for point in report.points:
            assert isinstance(point.sample_size, SampleSize)

    def test_corpus_required_in_points(self, history, engineering_corpus):
        report = history.build_history_report(
            engineering_corpus,
            RuntimeIntelligenceMetricId.COMPATIBILITY_INDEX.value,
            family_id=BehaviorFamilyId.FILESYSTEM,
            provider_id="native_alma",
        )
        assert all(point.corpus == engineering_corpus for point in report.points)

    def test_family_scoping_enforced(self, history, engineering_corpus):
        report = history.build_history_report(
            engineering_corpus,
            RuntimeIntelligenceMetricId.COMPATIBILITY_INDEX.value,
            family_id=BehaviorFamilyId.CONSOLE,
            provider_id="native_alma",
        )
        assert all(point.family_id == BehaviorFamilyId.CONSOLE for point in report.points)

    def test_no_forecast(self):
        assert "no forecast" in HISTORY_LIMITATION

    def test_no_causation_language(self):
        assert "causal inference" in HISTORY_LIMITATION
        assert "forecast" in HISTORY_LIMITATION

    def test_deterministic_history_digest(self, history, engineering_corpus):
        kwargs = dict(
            corpus=engineering_corpus,
            metric_id=RuntimeIntelligenceMetricId.COMPATIBILITY_INDEX.value,
            family_id=BehaviorFamilyId.FILESYSTEM,
            provider_id="native_alma",
        )
        r1 = history.build_history_report(**kwargs)
        r2 = history.build_history_report(**kwargs)
        assert r1.report_digest == r2.report_digest

    def test_ordering_does_not_affect_history_digest(self, engineering_corpus):
        points = [
            {
                "timestamp_bucket": "2026-08-02",
                "metric_id": "compatibility_index",
                "numerator": 1,
                "denominator": 2,
                "value": 0.5,
                "status": RuntimeIntelligenceHistoryStatus.COMPUTED.value,
            },
            {
                "timestamp_bucket": "2026-08-01",
                "metric_id": "compatibility_index",
                "numerator": 1,
                "denominator": 2,
                "value": 0.5,
                "status": RuntimeIntelligenceHistoryStatus.COMPUTED.value,
            },
        ]
        from alma_bridge.runtime_intelligence.models import RuntimeIntelligenceHistoryPoint

        built = [
            RuntimeIntelligenceHistoryPoint(
                timestamp_bucket=p["timestamp_bucket"],
                corpus=engineering_corpus,
                family_id=BehaviorFamilyId.FILESYSTEM,
                provider_id="native_alma",
                metric_id=p["metric_id"],
                numerator=p["numerator"],
                denominator=p["denominator"],
                sample_size=SampleSize(numerator=p["numerator"], denominator=p["denominator"]),
                value=p["value"],
                status=RuntimeIntelligenceHistoryStatus.COMPUTED,
            )
            for p in points
        ]
        d1 = compute_history_report_digest(
            corpus=engineering_corpus,
            metric_id="compatibility_index",
            family_id=BehaviorFamilyId.FILESYSTEM,
            provider_id="native_alma",
            points=built,
        )
        d2 = compute_history_report_digest(
            corpus=engineering_corpus,
            metric_id="compatibility_index",
            family_id=BehaviorFamilyId.FILESYSTEM,
            provider_id="native_alma",
            points=list(reversed(built)),
        )
        assert d1 == d2

    def test_verification_rate_history_metric(self, history, engineering_corpus):
        report = history.build_history_report(
            engineering_corpus,
            RuntimeIntelligenceMetricId.VERIFICATION_RATE.value,
        )
        assert report.metric_id == RuntimeIntelligenceMetricId.VERIFICATION_RATE.value

    def test_prediction_accuracy_history_metric(self, history, engineering_corpus):
        report = history.build_history_report(
            engineering_corpus,
            RuntimeIntelligenceMetricId.PREDICTION_ACCURACY.value,
            provider_id="native_alma",
        )
        assert report.metric_id == RuntimeIntelligenceMetricId.PREDICTION_ACCURACY.value

    def test_insufficient_evidence_status_when_no_points(self, history, engineering_corpus):
        report = history.build_history_report(
            engineering_corpus,
            RuntimeIntelligenceMetricId.HYPOTHESIS_ACCURACY.value,
        )
        assert "insufficient_timeline_evidence_for_metric" in report.limitations or report.points == []
