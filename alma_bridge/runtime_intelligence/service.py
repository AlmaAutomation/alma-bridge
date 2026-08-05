"""Runtime Intelligence orchestration — read-only reports and append-only hypothesis timeline."""

from __future__ import annotations

from typing import List, Optional

from alma_bridge.evidence.digest import compute_event_id
from alma_bridge.evidence.models import Provenance, TimelineEvent, TimelineEventType, utc_now_iso
from alma_bridge.evidence.queries import EvidenceQueries
from alma_bridge.evidence.repository import EvidenceRepository
from alma_bridge.runtime_intelligence.debt import build_debt_report
from alma_bridge.runtime_intelligence.family import CANONICAL_FAMILIES, list_families
from alma_bridge.runtime_intelligence.hypotheses import (
    HYPOTHESIS_EVENT_TYPE_CREATED,
    HYPOTHESIS_EVENT_TYPE_OUTCOME_LINKED,
    build_hypothesis_created_event_payload,
    build_hypothesis_outcome_linked_event_payload,
    evaluate_hypothesis,
)
from alma_bridge.runtime_intelligence.history import RuntimeIntelligenceHistory
from alma_bridge.runtime_intelligence.index import compute_compatibility_index
from alma_bridge.runtime_intelligence.knowledge import compute_knowledge_coverage
from alma_bridge.runtime_intelligence.models import (
    BehaviorFamilyId,
    CompatibilityDebtReport,
    CompatibilityIndexReport,
    CompatibilityKnowledgeCoverageReport,
    CorpusKind,
    EngineeringHypothesisEvaluation,
    EngineeringHypothesisOutcomeLink,
    EngineeringHypothesisSnapshot,
    HypothesisNotFoundError,
    HypothesisTimelineConflictError,
    InvalidFamilyError,
    RuntimeIntelligenceFamilySummary,
    RuntimeIntelligenceHypothesisSummary,
    RuntimeIntelligenceMetricId,
    RuntimeIntelligenceReport,
    TimelineAppendResult,
    TimelineAppendStatus,
    compute_runtime_intelligence_report_digest,
)
from alma_bridge.runtime_intelligence.queries import RuntimeIntelligenceQueries


class RuntimeIntelligenceService:
    """Read-only Runtime Intelligence service with append-only hypothesis timeline."""

    _instance: Optional["RuntimeIntelligenceService"] = None

    def __init__(
        self,
        *,
        queries: Optional[RuntimeIntelligenceQueries] = None,
        history: Optional[RuntimeIntelligenceHistory] = None,
        evidence_queries: Optional[EvidenceQueries] = None,
        evidence_repo: Optional[EvidenceRepository] = None,
    ) -> None:
        self._queries = queries or RuntimeIntelligenceQueries()
        self._history = history or RuntimeIntelligenceHistory(self._queries)
        self._evidence = evidence_queries or EvidenceQueries(evidence_repo)
        self._repo = evidence_repo or EvidenceRepository()

    @classmethod
    def shared(cls) -> "RuntimeIntelligenceService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def parse_corpus(value: str) -> CorpusKind:
        try:
            return CorpusKind(value)
        except ValueError as exc:
            from alma_bridge.runtime_intelligence.models import InvalidCorpusError

            raise InvalidCorpusError(f"invalid corpus: {value}") from exc

    @staticmethod
    def parse_family(value: str) -> BehaviorFamilyId:
        try:
            return BehaviorFamilyId(value)
        except ValueError as exc:
            raise InvalidFamilyError(f"invalid family_id: {value}") from exc

    def get_families(self, corpus: CorpusKind) -> List[RuntimeIntelligenceFamilySummary]:
        enrolled = self._queries.enrolled_entries(corpus)
        summaries: List[RuntimeIntelligenceFamilySummary] = []
        for family_id in list_families():
            canonical = CANONICAL_FAMILIES[family_id]
            capabilities = self._queries._capabilities_for_family(family_id)
            count = len(enrolled) if capabilities else 0
            summaries.append(
                RuntimeIntelligenceFamilySummary(
                    family_id=family_id,
                    name=canonical.name,
                    description=canonical.description,
                    enrolled_application_count=count,
                )
            )
        return summaries

    def get_family(self, corpus: CorpusKind, family_id: BehaviorFamilyId) -> RuntimeIntelligenceFamilySummary:
        summaries = self.get_families(corpus)
        for summary in summaries:
            if summary.family_id == family_id:
                return summary
        raise InvalidFamilyError(f"family not available for corpus: {family_id.value}")

    def get_index(
        self,
        corpus: CorpusKind,
        family_id: BehaviorFamilyId,
        provider_id: str,
    ) -> CompatibilityIndexReport:
        digest = self._queries.compute_evidence_snapshot_digest(
            corpus, family_id=family_id, provider_id=provider_id
        )
        input_data, _ = self._queries.build_index_input(corpus, family_id, provider_id, digest)
        return compute_compatibility_index(input_data)

    def get_knowledge(
        self,
        corpus: CorpusKind,
        family_id: BehaviorFamilyId,
        provider_id: str,
    ) -> CompatibilityKnowledgeCoverageReport:
        digest = self._queries.compute_evidence_snapshot_digest(
            corpus, family_id=family_id, provider_id=provider_id
        )
        input_data, _ = self._queries.build_knowledge_input(corpus, family_id, provider_id, digest)
        return compute_knowledge_coverage(input_data)

    def get_debt(
        self,
        corpus: CorpusKind,
        family_id: BehaviorFamilyId,
        provider_id: str,
    ) -> CompatibilityDebtReport:
        digest = self._queries.compute_evidence_snapshot_digest(
            corpus, family_id=family_id, provider_id=provider_id
        )
        signals, metadata = self._queries.build_debt_signals(corpus, family_id, provider_id, digest)
        return build_debt_report(
            corpus=corpus,
            family_id=family_id,
            signals=signals,
            provider_id=provider_id,
            evidence_snapshot_digest=digest,
            limitations=metadata.limitations,
        )

    def list_hypotheses(
        self,
        corpus: CorpusKind,
        *,
        family_id: Optional[BehaviorFamilyId] = None,
    ) -> List[EngineeringHypothesisSnapshot]:
        snapshots, _ = self._queries.build_hypothesis_snapshot_inputs(corpus, family_id=family_id)
        return sorted(snapshots, key=lambda s: s.created_at)

    def get_hypothesis(self, corpus: CorpusKind, hypothesis_id: str) -> EngineeringHypothesisEvaluation:
        snapshots = self.list_hypotheses(corpus)
        snapshot = next((s for s in snapshots if s.hypothesis_id == hypothesis_id), None)
        if snapshot is None:
            raise HypothesisNotFoundError(f"hypothesis not found: {hypothesis_id}")
        links, _ = self._queries.build_hypothesis_outcome_links(corpus, hypothesis_id=hypothesis_id)
        return evaluate_hypothesis(snapshot=snapshot, outcome_links=links)

    def get_history(
        self,
        corpus: CorpusKind,
        metric_id: str,
        *,
        family_id: Optional[BehaviorFamilyId] = None,
        provider_id: Optional[str] = None,
    ):
        return self._history.build_history_report(
            corpus,
            metric_id,
            family_id=family_id,
            provider_id=provider_id,
        )

    def get_report(self, corpus: CorpusKind, *, provider_id: str = "native_alma") -> RuntimeIntelligenceReport:
        generated_at = utc_now_iso()
        family_summaries = self.get_families(corpus)
        indexes: List[CompatibilityIndexReport] = []
        knowledge_reports: List[CompatibilityKnowledgeCoverageReport] = []
        debt_reports: List[CompatibilityDebtReport] = []
        all_refs: List[str] = []
        limitations: List[str] = []
        excluded_total = 0

        active_families = [
            BehaviorFamilyId.FILESYSTEM,
            BehaviorFamilyId.CONSOLE,
            BehaviorFamilyId.CRT,
        ]
        digest = self._queries.compute_evidence_snapshot_digest(
            corpus,
            family_id=BehaviorFamilyId.FILESYSTEM,
            provider_id=provider_id,
        )

        for family_id in active_families:
            index_report = self.get_index(corpus, family_id, provider_id)
            indexes.append(index_report)
            all_refs.extend(index_report.evidence_references)
            limitations.extend(index_report.limitations)

            knowledge_report = self.get_knowledge(corpus, family_id, provider_id)
            knowledge_reports.append(knowledge_report)
            all_refs.extend(knowledge_report.evidence_references)

            debt_report = self.get_debt(corpus, family_id, provider_id)
            debt_reports.append(debt_report)
            all_refs.extend(debt_report.evidence_references)
            _, meta = self._queries.build_debt_signals(corpus, family_id, provider_id, digest)
            excluded_total += meta.excluded_unenrolled_artifact_count
            limitations.extend(meta.limitations)

        snapshots = self.list_hypotheses(corpus)
        by_result: dict[str, int] = {}
        for snapshot in snapshots:
            evaluation = self.get_hypothesis(corpus, snapshot.hypothesis_id)
            by_result[evaluation.result.value] = by_result.get(evaluation.result.value, 0) + 1

        hypothesis_summary = RuntimeIntelligenceHypothesisSummary(
            total_count=len(snapshots),
            by_result=by_result,
            limitations=["planning accuracy measurement only; not authorization to implement"],
        )

        history_summary = {
            metric.value: self.get_history(
                corpus, metric.value, family_id=BehaviorFamilyId.FILESYSTEM, provider_id=provider_id
            ).report_digest
            for metric in (
                RuntimeIntelligenceMetricId.COMPATIBILITY_INDEX,
                RuntimeIntelligenceMetricId.KNOWLEDGE_COVERAGE,
            )
        }

        report_digest = compute_runtime_intelligence_report_digest(
            corpus=corpus,
            evidence_snapshot_digest=digest,
            family_summaries=family_summaries,
            compatibility_indexes=indexes,
            knowledge_coverage=knowledge_reports,
            debt_reports=debt_reports,
            hypothesis_summary=hypothesis_summary,
            excluded_unenrolled_artifact_count=excluded_total,
            limitations=sorted(set(limitations)),
            evidence_references=sorted(set(all_refs)),
        )

        return RuntimeIntelligenceReport(
            corpus=corpus,
            generated_at=generated_at,
            evidence_snapshot_digest=digest,
            family_summaries=family_summaries,
            compatibility_indexes=indexes,
            knowledge_coverage=knowledge_reports,
            debt_reports=debt_reports,
            hypothesis_summary=hypothesis_summary,
            history_summary=history_summary,
            excluded_unenrolled_artifact_count=excluded_total,
            limitations=sorted(set(limitations)),
            evidence_references=sorted(set(all_refs)),
            report_digest=report_digest,
        )

    def _resolve_hypothesis_bundle_id(self, snapshot: EngineeringHypothesisSnapshot) -> str:
        for fingerprint in snapshot.predicted_application_fingerprints:
            if self._queries._corpus.is_enrolled(
                snapshot.corpus, application_fingerprint=fingerprint
            ):
                bundle = self._evidence.by_application_fingerprint(fingerprint)
                if bundle is not None:
                    return bundle.bundle_id
        return compute_event_id(
            {"kind": "runtime_intelligence_corpus_timeline", "corpus": snapshot.corpus.value}
        )

    def _resolve_outcome_link_bundle_id(self, link: EngineeringHypothesisOutcomeLink) -> str:
        for fingerprint in link.observed_application_fingerprints:
            bundle = self._evidence.by_application_fingerprint(fingerprint)
            if bundle is not None:
                return bundle.bundle_id
        for bundle_id in self._evidence.list_bundle_ids():
            for event in self._evidence.timeline(bundle_id):
                if (event.metadata or {}).get("hypothesis_id") == link.hypothesis_id:
                    return bundle_id
        return compute_event_id(
            {"kind": "runtime_intelligence_hypothesis", "hypothesis_id": link.hypothesis_id}
        )

    def _find_timeline_event(
        self,
        bundle_id: str,
        *,
        event_type: TimelineEventType,
        identity_key: str,
        identity_value: str,
    ) -> Optional[TimelineEvent]:
        for event in self._evidence.timeline(bundle_id):
            if event.event_type != event_type:
                continue
            metadata = event.metadata or {}
            if metadata.get(identity_key) == identity_value:
                return event
        return None

    def record_hypothesis_created(
        self, snapshot: EngineeringHypothesisSnapshot
    ) -> TimelineAppendResult:
        payload = build_hypothesis_created_event_payload(snapshot)
        event_id = compute_event_id(
            {
                "event_type": HYPOTHESIS_EVENT_TYPE_CREATED,
                "hypothesis_id": snapshot.hypothesis_id,
                "snapshot_digest": snapshot.snapshot_digest,
            }
        )
        bundle_id = self._resolve_hypothesis_bundle_id(snapshot)
        existing = self._find_timeline_event(
            bundle_id,
            event_type=TimelineEventType.ENGINEERING_HYPOTHESIS_CREATED,
            identity_key="hypothesis_id",
            identity_value=snapshot.hypothesis_id,
        )
        if existing is not None:
            if existing.evidence_digest == snapshot.snapshot_digest:
                return TimelineAppendResult(
                    status=TimelineAppendStatus.DUPLICATE,
                    event_id=existing.event_id,
                    bundle_id=bundle_id,
                )
            raise HypothesisTimelineConflictError(
                f"conflicting immutable hypothesis snapshot for {snapshot.hypothesis_id}"
            )

        event = TimelineEvent(
            event_id=event_id,
            event_type=TimelineEventType.ENGINEERING_HYPOTHESIS_CREATED,
            timestamp=snapshot.created_at,
            version=len(self._evidence.timeline(bundle_id)) + 1,
            evidence_digest=snapshot.snapshot_digest,
            source="runtime_intelligence",
            references=[snapshot.hypothesis_id],
            provenance=Provenance(
                source="runtime_intelligence",
                artifact_id=snapshot.hypothesis_id,
                digest=snapshot.snapshot_digest,
            ),
            metadata={**payload, "formula_version": snapshot.formula_version},
        )
        self._repo.append_timeline_event(bundle_id, event)
        return TimelineAppendResult(
            status=TimelineAppendStatus.APPENDED,
            event_id=event_id,
            bundle_id=bundle_id,
        )

    def record_hypothesis_outcome_linked(
        self, link: EngineeringHypothesisOutcomeLink
    ) -> TimelineAppendResult:
        payload = build_hypothesis_outcome_linked_event_payload(link)
        event_id = compute_event_id(
            {
                "event_type": HYPOTHESIS_EVENT_TYPE_OUTCOME_LINKED,
                "outcome_link_id": link.outcome_link_id,
                "link_digest": link.link_digest,
            }
        )
        bundle_id = self._resolve_outcome_link_bundle_id(link)
        existing = self._find_timeline_event(
            bundle_id,
            event_type=TimelineEventType.ENGINEERING_HYPOTHESIS_OUTCOME_LINKED,
            identity_key="outcome_link_id",
            identity_value=link.outcome_link_id,
        )
        if existing is not None:
            if existing.evidence_digest == link.link_digest:
                return TimelineAppendResult(
                    status=TimelineAppendStatus.DUPLICATE,
                    event_id=existing.event_id,
                    bundle_id=bundle_id,
                )
            raise HypothesisTimelineConflictError(
                f"conflicting immutable outcome link for {link.outcome_link_id}"
            )

        event = TimelineEvent(
            event_id=event_id,
            event_type=TimelineEventType.ENGINEERING_HYPOTHESIS_OUTCOME_LINKED,
            timestamp=link.linked_at,
            version=len(self._evidence.timeline(bundle_id)) + 1,
            evidence_digest=link.link_digest,
            source="runtime_intelligence",
            references=[link.hypothesis_id, link.outcome_link_id],
            provenance=Provenance(
                source="runtime_intelligence",
                artifact_id=link.outcome_link_id,
                digest=link.link_digest,
            ),
            metadata=payload,
        )
        self._repo.append_timeline_event(bundle_id, event)
        return TimelineAppendResult(
            status=TimelineAppendStatus.APPENDED,
            event_id=event_id,
            bundle_id=bundle_id,
        )
