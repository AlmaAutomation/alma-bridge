"""Read-only historical trend models derived from evidence timeline."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from alma_bridge.research.models import SampleSize, TimeWindow
from alma_bridge.runtime_intelligence.hypotheses import evaluate_hypothesis
from alma_bridge.runtime_intelligence.models import (
    BehaviorFamilyId,
    CorpusKind,
    RuntimeIntelligenceHistoryPoint,
    RuntimeIntelligenceHistoryReport,
    RuntimeIntelligenceHistoryStatus,
    RuntimeIntelligenceMetricId,
    compute_history_report_digest,
)
from alma_bridge.runtime_intelligence.queries import RuntimeIntelligenceQueries, _bucket_key


HISTORY_LIMITATION = "observed trend only; no forecast or causal inference"


class RuntimeIntelligenceHistory:
    """Read-only trend aggregation from timeline and versioned records."""

    def __init__(self, queries: Optional[RuntimeIntelligenceQueries] = None) -> None:
        self._queries = queries or RuntimeIntelligenceQueries()

    def build_history_report(
        self,
        corpus: CorpusKind,
        metric_id: str,
        *,
        family_id: Optional[BehaviorFamilyId] = None,
        provider_id: Optional[str] = None,
        time_window: Optional[TimeWindow] = None,
    ) -> RuntimeIntelligenceHistoryReport:
        metric = RuntimeIntelligenceMetricId(metric_id)
        if metric == RuntimeIntelligenceMetricId.COMPATIBILITY_INDEX:
            points = self._index_history(corpus, family_id=family_id, provider_id=provider_id)
        elif metric == RuntimeIntelligenceMetricId.KNOWLEDGE_COVERAGE:
            points = self._knowledge_history(corpus, family_id=family_id, provider_id=provider_id)
        elif metric == RuntimeIntelligenceMetricId.COMPATIBILITY_DEBT:
            points = self._debt_history(corpus, family_id=family_id, provider_id=provider_id)
        elif metric == RuntimeIntelligenceMetricId.HYPOTHESIS_ACCURACY:
            points = self._hypothesis_accuracy_history(corpus, family_id=family_id, provider_id=provider_id)
        elif metric == RuntimeIntelligenceMetricId.VERIFICATION_RATE:
            points = self._verification_rate_history(corpus, family_id=family_id, provider_id=provider_id)
        elif metric == RuntimeIntelligenceMetricId.PREDICTION_ACCURACY:
            points = self._prediction_accuracy_history(corpus, family_id=family_id, provider_id=provider_id)
        elif metric == RuntimeIntelligenceMetricId.DETERMINISM_RATE:
            points = self._determinism_rate_history(corpus, family_id=family_id, provider_id=provider_id)
        elif metric == RuntimeIntelligenceMetricId.APPLICATIONS_UNLOCKED:
            points = self._applications_unlocked_history(corpus, family_id=family_id, provider_id=provider_id)
        elif metric == RuntimeIntelligenceMetricId.APPLICATION_CLASSES_UNLOCKED:
            points = self._application_classes_unlocked_history(
                corpus, family_id=family_id, provider_id=provider_id
            )
        else:
            points = []

        limitations = [HISTORY_LIMITATION]
        if not points:
            limitations.append("insufficient_timeline_evidence_for_metric")

        digest = compute_history_report_digest(
            corpus=corpus,
            metric_id=metric_id,
            family_id=family_id,
            provider_id=provider_id,
            points=points,
        )
        return RuntimeIntelligenceHistoryReport(
            corpus=corpus,
            metric_id=metric_id,
            family_id=family_id,
            provider_id=provider_id,
            points=points,
            report_digest=digest,
            limitations=limitations,
        )

    def _scoped_provider(self, provider_id: Optional[str]) -> str:
        return provider_id or "native_alma"

    def _index_history(
        self,
        corpus: CorpusKind,
        *,
        family_id: Optional[BehaviorFamilyId],
        provider_id: Optional[str],
    ) -> List[RuntimeIntelligenceHistoryPoint]:
        if family_id is None:
            return []
        provider = self._scoped_provider(provider_id)
        digest = self._queries.compute_evidence_snapshot_digest(
            corpus, family_id=family_id, provider_id=provider
        )
        input_data, _ = self._queries.build_index_input(corpus, family_id, provider, digest)
        from alma_bridge.runtime_intelligence.index import compute_compatibility_index

        report = compute_compatibility_index(input_data)
        if report.index_value is None:
            return [
                RuntimeIntelligenceHistoryPoint(
                    timestamp_bucket="current",
                    corpus=corpus,
                    family_id=family_id,
                    provider_id=provider,
                    metric_id=RuntimeIntelligenceMetricId.COMPATIBILITY_INDEX.value,
                    numerator=0,
                    denominator=0,
                    sample_size=SampleSize(),
                    value=None,
                    status=RuntimeIntelligenceHistoryStatus.INSUFFICIENT_EVIDENCE,
                )
            ]
        available = [c for c in report.components if c.available]
        num = sum(1 for c in available if c.value is not None)
        den = len(available)
        return [
            RuntimeIntelligenceHistoryPoint(
                timestamp_bucket="current",
                corpus=corpus,
                family_id=family_id,
                provider_id=provider,
                metric_id=RuntimeIntelligenceMetricId.COMPATIBILITY_INDEX.value,
                numerator=num,
                denominator=den,
                sample_size=SampleSize(numerator=num, denominator=den),
                value=report.index_value,
                evidence_references=report.evidence_references,
                status=RuntimeIntelligenceHistoryStatus.COMPUTED,
            )
        ]

    def _knowledge_history(
        self,
        corpus: CorpusKind,
        *,
        family_id: Optional[BehaviorFamilyId],
        provider_id: Optional[str],
    ) -> List[RuntimeIntelligenceHistoryPoint]:
        if family_id is None:
            return []
        provider = self._scoped_provider(provider_id)
        digest = self._queries.compute_evidence_snapshot_digest(
            corpus, family_id=family_id, provider_id=provider
        )
        input_data, _ = self._queries.build_knowledge_input(corpus, family_id, provider, digest)
        from alma_bridge.runtime_intelligence.knowledge import compute_knowledge_coverage

        report = compute_knowledge_coverage(input_data)
        if report.knowledge_coverage_value is None:
            return [
                RuntimeIntelligenceHistoryPoint(
                    timestamp_bucket="current",
                    corpus=corpus,
                    family_id=family_id,
                    provider_id=provider,
                    metric_id=RuntimeIntelligenceMetricId.KNOWLEDGE_COVERAGE.value,
                    numerator=0,
                    denominator=0,
                    sample_size=SampleSize(),
                    value=None,
                    status=RuntimeIntelligenceHistoryStatus.INSUFFICIENT_EVIDENCE,
                )
            ]
        available = [c for c in report.components if c.available]
        return [
            RuntimeIntelligenceHistoryPoint(
                timestamp_bucket="current",
                corpus=corpus,
                family_id=family_id,
                provider_id=provider,
                metric_id=RuntimeIntelligenceMetricId.KNOWLEDGE_COVERAGE.value,
                numerator=len(available),
                denominator=len(report.components),
                sample_size=SampleSize(numerator=len(available), denominator=len(report.components)),
                value=report.knowledge_coverage_value,
                evidence_references=report.evidence_references,
                status=RuntimeIntelligenceHistoryStatus.COMPUTED,
            )
        ]

    def _debt_history(
        self,
        corpus: CorpusKind,
        *,
        family_id: Optional[BehaviorFamilyId],
        provider_id: Optional[str],
    ) -> List[RuntimeIntelligenceHistoryPoint]:
        if family_id is None:
            return []
        provider = self._scoped_provider(provider_id)
        digest = self._queries.compute_evidence_snapshot_digest(
            corpus, family_id=family_id, provider_id=provider
        )
        signals, _ = self._queries.build_debt_signals(corpus, family_id, provider, digest)
        from alma_bridge.runtime_intelligence.debt import build_debt_report

        report = build_debt_report(
            corpus=corpus,
            family_id=family_id,
            signals=signals,
            provider_id=provider,
            evidence_snapshot_digest=digest,
        )
        return [
            RuntimeIntelligenceHistoryPoint(
                timestamp_bucket="current",
                corpus=corpus,
                family_id=family_id,
                provider_id=provider,
                metric_id=RuntimeIntelligenceMetricId.COMPATIBILITY_DEBT.value,
                numerator=len(report.items),
                denominator=max(len(report.items), 1),
                sample_size=SampleSize(
                    numerator=len(report.items),
                    denominator=max(len(report.items), 1),
                ),
                value=float(len(report.items)) if len(report.items) <= 1 else None,
                evidence_references=report.evidence_references,
                status=RuntimeIntelligenceHistoryStatus.COMPUTED,
            )
        ]

    def _hypothesis_accuracy_history(
        self,
        corpus: CorpusKind,
        *,
        family_id: Optional[BehaviorFamilyId],
        provider_id: Optional[str],
    ) -> List[RuntimeIntelligenceHistoryPoint]:
        snapshots, links = self._queries.list_hypothesis_timeline_events(corpus)
        if family_id is not None:
            snapshots = [s for s in snapshots if s.family_id == family_id]
        if provider_id is not None:
            snapshots = [s for s in snapshots if s.provider_id == provider_id]

        buckets: Dict[str, Dict[str, int]] = defaultdict(lambda: {"correct": 0, "total": 0})
        refs: List[str] = []
        for snapshot in snapshots:
            scoped_links = [link for link in links if link.hypothesis_id == snapshot.hypothesis_id]
            evaluation = evaluate_hypothesis(snapshot=snapshot, outcome_links=scoped_links)
            bucket = _bucket_key(snapshot.created_at)
            buckets[bucket]["total"] += 1
            if evaluation.result.value in ("confirmed", "partially_confirmed"):
                buckets[bucket]["correct"] += 1
            refs.extend(evaluation.evidence_references)

        points: List[RuntimeIntelligenceHistoryPoint] = []
        for bucket in sorted(buckets.keys()):
            data = buckets[bucket]
            if data["total"] == 0:
                continue
            value = round(data["correct"] / data["total"], 4)
            points.append(
                RuntimeIntelligenceHistoryPoint(
                    timestamp_bucket=bucket,
                    corpus=corpus,
                    family_id=family_id,
                    provider_id=provider_id,
                    metric_id=RuntimeIntelligenceMetricId.HYPOTHESIS_ACCURACY.value,
                    numerator=data["correct"],
                    denominator=data["total"],
                    sample_size=SampleSize(numerator=data["correct"], denominator=data["total"], label=bucket),
                    value=value,
                    evidence_references=sorted(set(refs)),
                    status=RuntimeIntelligenceHistoryStatus.COMPUTED,
                )
            )
        return points

    def _verification_rate_history(
        self,
        corpus: CorpusKind,
        *,
        family_id: Optional[BehaviorFamilyId],
        provider_id: Optional[str],
    ) -> List[RuntimeIntelligenceHistoryPoint]:
        enrolled_digests = {
            entry.binary_digest for entry in self._queries.enrolled_entries(corpus)
        }
        if not enrolled_digests:
            return []

        buckets: Dict[str, Dict[str, int]] = defaultdict(lambda: {"verified": 0, "total": 0})
        for artifact in self._queries.enrolled_entries(corpus):
            bundle = self._queries._evidence.by_binary_digest(artifact.binary_digest)
            if bundle is None:
                continue
            for event in self._queries._evidence.timeline(bundle.bundle_id):
                if event.event_type.value != "VerificationCompleted":
                    continue
                bucket = _bucket_key(event.timestamp)
                buckets[bucket]["total"] += 1
                if event.metadata.get("verified"):
                    buckets[bucket]["verified"] += 1

        points: List[RuntimeIntelligenceHistoryPoint] = []
        for bucket in sorted(buckets.keys()):
            data = buckets[bucket]
            if data["total"] == 0:
                continue
            points.append(
                RuntimeIntelligenceHistoryPoint(
                    timestamp_bucket=bucket,
                    corpus=corpus,
                    family_id=family_id,
                    provider_id=provider_id,
                    metric_id=RuntimeIntelligenceMetricId.VERIFICATION_RATE.value,
                    numerator=data["verified"],
                    denominator=data["total"],
                    sample_size=SampleSize(numerator=data["verified"], denominator=data["total"], label=bucket),
                    value=round(data["verified"] / data["total"], 4),
                    status=RuntimeIntelligenceHistoryStatus.COMPUTED,
                )
            )
        return points

    def _prediction_accuracy_history(
        self,
        corpus: CorpusKind,
        *,
        family_id: Optional[BehaviorFamilyId],
        provider_id: Optional[str],
    ) -> List[RuntimeIntelligenceHistoryPoint]:
        buckets: Dict[str, Dict[str, int]] = defaultdict(lambda: {"correct": 0, "total": 0})
        for record in self._queries._calibration.list_records(limit=500):
            if provider_id and record.get("provider_id") != provider_id:
                continue
            if family_id and self._queries._capabilities_for_family(family_id):
                cap = record.get("capability_id", "")
                from alma_bridge.runtime_intelligence.family import family_for_capability

                if family_for_capability(cap) != family_id:
                    continue
            if not self._queries._corpus.is_enrolled(
                corpus,
                binary_digest=record.get("binary_digest"),
                application_fingerprint=record.get("application_fingerprint"),
            ):
                continue
            bucket = _bucket_key(record.get("created_at", ""))
            classification = record.get("classification", "")
            if classification in ("indeterminate", ""):
                continue
            buckets[bucket]["total"] += 1
            if classification in ("true_positive", "true_negative"):
                buckets[bucket]["correct"] += 1

        points: List[RuntimeIntelligenceHistoryPoint] = []
        for bucket in sorted(buckets.keys()):
            data = buckets[bucket]
            if data["total"] == 0:
                continue
            points.append(
                RuntimeIntelligenceHistoryPoint(
                    timestamp_bucket=bucket,
                    corpus=corpus,
                    family_id=family_id,
                    provider_id=provider_id,
                    metric_id=RuntimeIntelligenceMetricId.PREDICTION_ACCURACY.value,
                    numerator=data["correct"],
                    denominator=data["total"],
                    sample_size=SampleSize(numerator=data["correct"], denominator=data["total"], label=bucket),
                    value=round(data["correct"] / data["total"], 4),
                    status=RuntimeIntelligenceHistoryStatus.COMPUTED,
                )
            )
        return points

    def _determinism_rate_history(
        self,
        corpus: CorpusKind,
        *,
        family_id: Optional[BehaviorFamilyId],
        provider_id: Optional[str],
    ) -> List[RuntimeIntelligenceHistoryPoint]:
        return self._prediction_accuracy_history(
            corpus, family_id=family_id, provider_id=provider_id
        )

    def _applications_unlocked_history(
        self,
        corpus: CorpusKind,
        *,
        family_id: Optional[BehaviorFamilyId],
        provider_id: Optional[str],
    ) -> List[RuntimeIntelligenceHistoryPoint]:
        snapshots, links = self._queries.list_hypothesis_timeline_events(corpus)
        buckets: Dict[str, int] = defaultdict(int)
        refs: List[str] = []
        for snapshot in snapshots:
            if family_id and snapshot.family_id != family_id:
                continue
            if provider_id and snapshot.provider_id != provider_id:
                continue
            scoped_links = [link for link in links if link.hypothesis_id == snapshot.hypothesis_id]
            evaluation = evaluate_hypothesis(snapshot=snapshot, outcome_links=scoped_links)
            bucket = _bucket_key(snapshot.created_at)
            buckets[bucket] += evaluation.observed_applications_unblocked_count
            refs.extend(evaluation.evidence_references)

        points: List[RuntimeIntelligenceHistoryPoint] = []
        for bucket in sorted(buckets.keys()):
            count = buckets[bucket]
            if count == 0:
                continue
            points.append(
                RuntimeIntelligenceHistoryPoint(
                    timestamp_bucket=bucket,
                    corpus=corpus,
                    family_id=family_id,
                    provider_id=provider_id,
                    metric_id=RuntimeIntelligenceMetricId.APPLICATIONS_UNLOCKED.value,
                    numerator=count,
                    denominator=count,
                    sample_size=SampleSize(numerator=count, denominator=count, label=bucket),
                    value=float(count) if count <= 1 else None,
                    evidence_references=sorted(set(refs)),
                    status=RuntimeIntelligenceHistoryStatus.COMPUTED,
                )
            )
        return points

    def _application_classes_unlocked_history(
        self,
        corpus: CorpusKind,
        *,
        family_id: Optional[BehaviorFamilyId],
        provider_id: Optional[str],
    ) -> List[RuntimeIntelligenceHistoryPoint]:
        snapshots, links = self._queries.list_hypothesis_timeline_events(corpus)
        buckets: Dict[str, int] = defaultdict(int)
        for snapshot in snapshots:
            if family_id and snapshot.family_id != family_id:
                continue
            if provider_id and snapshot.provider_id != provider_id:
                continue
            scoped_links = [link for link in links if link.hypothesis_id == snapshot.hypothesis_id]
            evaluation = evaluate_hypothesis(snapshot=snapshot, outcome_links=scoped_links)
            bucket = _bucket_key(snapshot.created_at)
            buckets[bucket] += evaluation.observed_application_classes_unblocked_count

        points: List[RuntimeIntelligenceHistoryPoint] = []
        for bucket in sorted(buckets.keys()):
            count = buckets[bucket]
            if count == 0:
                continue
            points.append(
                RuntimeIntelligenceHistoryPoint(
                    timestamp_bucket=bucket,
                    corpus=corpus,
                    family_id=family_id,
                    provider_id=provider_id,
                    metric_id=RuntimeIntelligenceMetricId.APPLICATION_CLASSES_UNLOCKED.value,
                    numerator=count,
                    denominator=count,
                    sample_size=SampleSize(numerator=count, denominator=count, label=bucket),
                    value=float(count) if count <= 1 else None,
                    status=RuntimeIntelligenceHistoryStatus.COMPUTED,
                )
            )
        return points
