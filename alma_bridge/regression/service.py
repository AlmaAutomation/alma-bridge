"""Compatibility Regression service — read-only profile comparison."""

from __future__ import annotations

from typing import List, Optional

from alma_bridge.intelligence.evidence import EvidenceBundleBuilder
from alma_bridge.intelligence.models import IntelligenceNotFoundError, MalformedEvidenceError
from alma_bridge.knowledge.aggregation import KnowledgeAggregationEngine
from alma_bridge.knowledge.models import MalformedKnowledgeEvidenceError
from alma_bridge.regression.diff import RegressionDiffEngine
from alma_bridge.regression.models import (
    CompatibilityRegressionReport,
    RegressionFinding,
    RegressionNotFoundError,
)
from alma_bridge.regression.queries import (
    filter_evidence_bundle,
    latest_session_id,
    sort_sessions,
)
from alma_bridge.regression.repository import (
    ReadOnlyRegressionEvidenceAdapter,
    RegressionEvidenceRepository,
)


class CompatibilityRegressionService:
    """Read-only regression comparison backed by knowledge profile snapshots."""

    def __init__(
        self,
        repository: RegressionEvidenceRepository | None = None,
        aggregation_engine: KnowledgeAggregationEngine | None = None,
        diff_engine: RegressionDiffEngine | None = None,
    ) -> None:
        self._repository = repository or ReadOnlyRegressionEvidenceAdapter()
        self._builder = EvidenceBundleBuilder(self._repository)
        self._aggregation = aggregation_engine or KnowledgeAggregationEngine()
        self._diff = diff_engine or RegressionDiffEngine()

    def report_for_application(
        self,
        fingerprint: str,
        *,
        session_id: Optional[str] = None,
    ) -> CompatibilityRegressionReport:
        bundle = self._load_bundle(fingerprint)
        return self._compare_bundle(bundle, session_id=session_id)

    def report_for_session(self, session_id: str) -> CompatibilityRegressionReport:
        session = self._repository.get_session_record(session_id)
        if not session:
            raise RegressionNotFoundError(f"no session evidence for {session_id}")
        fingerprint = str(session.get("file_hash") or "")
        if not fingerprint:
            raise RegressionNotFoundError(f"session {session_id} has no application fingerprint")
        bundle = self._load_bundle(fingerprint)
        return self._compare_bundle(bundle, session_id=session_id)

    def _load_bundle(self, fingerprint: str):
        try:
            return self._builder.for_application(fingerprint)
        except IntelligenceNotFoundError as exc:
            raise RegressionNotFoundError(str(exc)) from exc
        except MalformedEvidenceError as exc:
            raise MalformedKnowledgeEvidenceError(str(exc), details=exc.details) from exc

    def _compare_bundle(self, bundle, *, session_id: Optional[str]) -> CompatibilityRegressionReport:
        sessions = sort_sessions(bundle.artifacts.get("sessions") or [])
        if not sessions:
            raise RegressionNotFoundError("evidence bundle contains no sessions")

        comparison_session_id = session_id or latest_session_id(sessions)
        baseline_session_ids = [
            str(item["session_id"])
            for item in sessions
            if str(item["session_id"]) != comparison_session_id
        ]
        current_session_count = len(sessions)
        baseline_session_count = len(baseline_session_ids)

        if baseline_session_count == 0:
            return CompatibilityRegressionReport(
                application_fingerprint=str(bundle.application_fingerprint or ""),
                application_name=self._application_name(bundle),
                comparison_session_id=comparison_session_id,
                baseline_session_count=0,
                current_session_count=current_session_count,
                unchanged_summary=(
                    "Insufficient baseline: first session for this application — "
                    "no prior sessions to compare."
                ),
            )

        baseline_bundle = filter_evidence_bundle(
            bundle,
            exclude_session_ids={comparison_session_id},
        )
        before = self._aggregate(baseline_bundle)
        after = self._aggregate(bundle)

        raw_findings = self._diff.compare(before, after)
        findings = self._enrich_findings(
            raw_findings,
            comparison_session_id=comparison_session_id,
            baseline_session_ids=baseline_session_ids,
            first_observed_at=self._session_started_at(sessions, comparison_session_id),
        )
        unchanged = self._diff.unchanged_summary(before, after, findings)

        return CompatibilityRegressionReport(
            application_fingerprint=after.application_fingerprint,
            application_name=after.application_name,
            comparison_session_id=comparison_session_id,
            baseline_session_count=baseline_session_count,
            current_session_count=current_session_count,
            regressions=findings,
            findings=findings,
            unchanged_summary=unchanged,
        )

    def _aggregate(self, bundle):
        try:
            return self._aggregation.aggregate(bundle)
        except MalformedKnowledgeEvidenceError:
            raise

    @staticmethod
    def _enrich_findings(
        findings: List[RegressionFinding],
        *,
        comparison_session_id: str,
        baseline_session_ids: List[str],
        first_observed_at: str,
    ) -> List[RegressionFinding]:
        enriched: List[RegressionFinding] = []
        for finding in findings:
            enriched.append(
                finding.model_copy(
                    update={
                        "comparison_session_id": comparison_session_id,
                        "baseline_session_ids": sorted(baseline_session_ids),
                        "first_observed_at": first_observed_at or finding.first_observed_at,
                    }
                )
            )
        return enriched

    @staticmethod
    def _session_started_at(sessions: list, session_id: str) -> str:
        for session in sessions:
            if str(session.get("session_id")) == session_id:
                return str(session.get("started_at") or "")
        return ""

    @staticmethod
    def _application_name(bundle) -> str:
        from pathlib import Path

        if bundle.file_path:
            return Path(bundle.file_path).name
        for session in bundle.artifacts.get("sessions") or []:
            file_path = session.get("file_path")
            if file_path:
                return Path(str(file_path)).name
        return str(bundle.application_fingerprint or "unknown")
