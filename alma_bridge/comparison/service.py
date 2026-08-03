"""Read-only session comparison service."""

from __future__ import annotations

from alma_bridge.comparison.diff import SessionComparisonDiffEngine
from alma_bridge.comparison.models import (
    ComparisonFingerprintMismatchError,
    ComparisonNotFoundError,
    MalformedComparisonEvidenceError,
    SessionEnvironmentComparison,
)
from alma_bridge.comparison.queries import build_session_evidence_snapshot
from alma_bridge.intelligence.evidence import EvidenceBundleBuilder
from alma_bridge.intelligence.models import IntelligenceNotFoundError, MalformedEvidenceError
from alma_bridge.knowledge.models import MalformedKnowledgeEvidenceError
from alma_bridge.knowledge.repository import ReadOnlyKnowledgeEvidenceAdapter


class SessionComparisonService:
    """Compare two sessions side-by-side using persisted evidence only."""

    def __init__(
        self,
        repository: ReadOnlyKnowledgeEvidenceAdapter | None = None,
        diff_engine: SessionComparisonDiffEngine | None = None,
    ) -> None:
        self._repository = repository or ReadOnlyKnowledgeEvidenceAdapter()
        self._builder = EvidenceBundleBuilder(self._repository)
        self._diff = diff_engine or SessionComparisonDiffEngine()

    def compare_sessions(
        self,
        baseline_session_id: str,
        comparison_session_id: str,
    ) -> SessionEnvironmentComparison:
        baseline_record = self._repository.get_session_record(baseline_session_id)
        comparison_record = self._repository.get_session_record(comparison_session_id)
        if not baseline_record:
            raise ComparisonNotFoundError(f"baseline session not found: {baseline_session_id}")
        if not comparison_record:
            raise ComparisonNotFoundError(
                f"comparison session not found: {comparison_session_id}"
            )

        baseline_fingerprint = str(baseline_record.get("file_hash") or "")
        comparison_fingerprint = str(comparison_record.get("file_hash") or "")
        if not baseline_fingerprint or not comparison_fingerprint:
            raise MalformedComparisonEvidenceError(
                "session evidence missing application fingerprint"
            )
        if baseline_fingerprint != comparison_fingerprint:
            raise ComparisonFingerprintMismatchError(
                "sessions must belong to the same application fingerprint"
            )

        baseline_bundle = self._load_bundle(baseline_session_id)
        comparison_bundle = self._load_bundle(comparison_session_id)
        before = self._snapshot(baseline_bundle, baseline_session_id)
        after = self._snapshot(comparison_bundle, comparison_session_id)
        return self._diff.compare(before, after)

    def compare_for_application(
        self,
        fingerprint: str,
        *,
        baseline_session_id: str,
        comparison_session_id: str,
    ) -> SessionEnvironmentComparison:
        report = self.compare_sessions(baseline_session_id, comparison_session_id)
        if report.application_fingerprint != fingerprint:
            raise ComparisonFingerprintMismatchError(
                "sessions do not match the requested application fingerprint"
            )
        return report

    def _load_bundle(self, session_id: str):
        try:
            return self._builder.for_session(session_id)
        except IntelligenceNotFoundError as exc:
            raise ComparisonNotFoundError(str(exc)) from exc
        except MalformedEvidenceError as exc:
            raise MalformedComparisonEvidenceError(str(exc), details=exc.details) from exc

    @staticmethod
    def _snapshot(bundle, session_id: str):
        try:
            return build_session_evidence_snapshot(bundle, session_id=session_id)
        except MalformedKnowledgeEvidenceError as exc:
            raise MalformedComparisonEvidenceError(str(exc)) from exc
