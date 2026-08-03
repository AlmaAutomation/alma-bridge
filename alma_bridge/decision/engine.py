"""Decision Engine — orchestrates read-only evidence into a deterministic plan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from alma_bridge.advisor.context import AdvisorContextBuilder
from alma_bridge.advisor.explanation import DeterministicAdvisorEngine
from alma_bridge.advisor.models import AdvisorExplanation, MalformedAdvisorError
from alma_bridge.advisor.queries import union_evidence_references
from alma_bridge.ask.models import AskAlmaQuestion
from alma_bridge.ask.service import AskAlmaService
from alma_bridge.comparison.models import (
    ComparisonFingerprintMismatchError,
    ComparisonNotFoundError,
    MalformedComparisonEvidenceError,
    SessionEnvironmentComparison,
)
from alma_bridge.comparison.service import SessionComparisonService
from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.decision.errors import DecisionNotFoundError, MalformedDecisionEvidenceError
from alma_bridge.decision.models import (
    DECISION_SCHEMA_VERSION,
    DecisionInput,
    DecisionPlan,
    EvidenceSummary,
)
from alma_bridge.decision.rules import DecisionRuleEvaluator
from alma_bridge.knowledge.models import CompatibilityKnowledgeProfile
from alma_bridge.regression.models import CompatibilityRegressionReport
from alma_bridge.regression.repository import ReadOnlyRegressionEvidenceAdapter


@dataclass(frozen=True)
class _DecisionSnapshot:
    application_fingerprint: str
    application_name: str
    session_id: Optional[str]
    knowledge: CompatibilityKnowledgeProfile
    regression: CompatibilityRegressionReport
    advisor: AdvisorExplanation
    comparison: Optional[SessionEnvironmentComparison]
    ask_summary: Optional[str]


class DecisionEngine:
    """Gather read-only evidence and evaluate deterministic decision rules."""

    def __init__(
        self,
        *,
        context_builder: AdvisorContextBuilder | None = None,
        advisor_engine: DeterministicAdvisorEngine | None = None,
        comparison_service: SessionComparisonService | None = None,
        ask_service: AskAlmaService | None = None,
        rule_evaluator: DecisionRuleEvaluator | None = None,
        repository: ReadOnlyRegressionEvidenceAdapter | None = None,
    ) -> None:
        self._context_builder = context_builder or AdvisorContextBuilder()
        self._advisor_engine = advisor_engine or DeterministicAdvisorEngine()
        self._comparison = comparison_service or SessionComparisonService()
        self._ask = ask_service or AskAlmaService()
        self._rules = rule_evaluator or DecisionRuleEvaluator()
        self._repository = repository or ReadOnlyRegressionEvidenceAdapter()

    def build_plan(self, decision_input: DecisionInput) -> DecisionPlan:
        snapshot = self._gather(decision_input)
        recommendations = self._rules.evaluate(
            application_fingerprint=snapshot.application_fingerprint,
            application_name=snapshot.application_name,
            knowledge=snapshot.knowledge,
            regression=snapshot.regression,
            advisor=snapshot.advisor,
            comparison=snapshot.comparison,
        )
        plan_id = self._plan_id(decision_input, snapshot)
        generated_at = self._generated_at(snapshot)
        notices = self._notices(snapshot)
        evidence_summary = EvidenceSummary(
            total_sessions=snapshot.knowledge.total_sessions,
            verified_successes=snapshot.knowledge.verified_successes,
            verified_failures=snapshot.knowledge.verified_failures,
            unverifiable_sessions=snapshot.knowledge.unverifiable_sessions,
            regression_finding_count=len(
                snapshot.regression.findings or snapshot.regression.regressions
            ),
            advisor_observation_count=len(snapshot.advisor.observations),
            comparison_included=snapshot.comparison is not None,
            ask_context_included=snapshot.ask_summary is not None,
        )
        return DecisionPlan(
            plan_id=plan_id,
            session_id=snapshot.session_id,
            application_fingerprint=snapshot.application_fingerprint,
            application_name=snapshot.application_name,
            generated_at=generated_at,
            recommendations=recommendations,
            evidence_summary=evidence_summary,
            notices=notices,
        )

    def _gather(self, decision_input: DecisionInput) -> _DecisionSnapshot:
        fingerprint, session_id = self._resolve_target(decision_input)
        try:
            context = self._context_builder.build(fingerprint, session_id=session_id)
            advisor = self._advisor_engine.explain(context)
        except MalformedAdvisorError as exc:
            raise MalformedDecisionEvidenceError(str(exc), details=exc.details) from exc

        comparison = self._maybe_compare(decision_input, fingerprint)
        ask_summary = self._maybe_ask(decision_input, fingerprint, session_id)

        return _DecisionSnapshot(
            application_fingerprint=context.application_fingerprint,
            application_name=context.application_name,
            session_id=session_id,
            knowledge=context.knowledge_profile,
            regression=context.regression_report,
            advisor=advisor,
            comparison=comparison,
            ask_summary=ask_summary,
        )

    def _resolve_target(self, decision_input: DecisionInput) -> tuple[str, Optional[str]]:
        if decision_input.session_id:
            session = self._repository.get_session_record(decision_input.session_id)
            if not session:
                raise DecisionNotFoundError(
                    f"no session evidence for {decision_input.session_id}"
                )
            fingerprint = str(session.get("file_hash") or "")
            if not fingerprint:
                raise DecisionNotFoundError(
                    f"session {decision_input.session_id} has no application fingerprint"
                )
            if (
                decision_input.application_fingerprint
                and decision_input.application_fingerprint != fingerprint
            ):
                raise MalformedDecisionEvidenceError(
                    "session_id does not match application_fingerprint"
                )
            return fingerprint, decision_input.session_id

        assert decision_input.application_fingerprint
        return decision_input.application_fingerprint, None

    def _maybe_compare(
        self,
        decision_input: DecisionInput,
        fingerprint: str,
    ) -> Optional[SessionEnvironmentComparison]:
        baseline = decision_input.baseline_session_id
        comparison_id = decision_input.comparison_session_id
        if not baseline or not comparison_id:
            return None
        try:
            return self._comparison.compare_for_application(
                fingerprint,
                baseline_session_id=baseline,
                comparison_session_id=comparison_id,
            )
        except ComparisonNotFoundError as exc:
            raise DecisionNotFoundError(str(exc)) from exc
        except ComparisonFingerprintMismatchError as exc:
            raise MalformedDecisionEvidenceError(str(exc)) from exc
        except MalformedComparisonEvidenceError as exc:
            raise MalformedDecisionEvidenceError(str(exc), details=exc.details) from exc

    def _maybe_ask(
        self,
        decision_input: DecisionInput,
        fingerprint: str,
        session_id: Optional[str],
    ) -> Optional[str]:
        question = (decision_input.ask_question or "").strip()
        if not question:
            return None
        answer = self._ask.ask(
            AskAlmaQuestion(
                question=question,
                application_fingerprint=fingerprint,
                session_id=session_id,
                render="deterministic",
            )
        )
        return answer.answer.strip() or None

    @staticmethod
    def _plan_id(decision_input: DecisionInput, snapshot: _DecisionSnapshot) -> str:
        payload = {
            "schema": DECISION_SCHEMA_VERSION,
            "input": decision_input.model_dump(mode="json", exclude_none=True),
            "application_fingerprint": snapshot.application_fingerprint,
            "session_id": snapshot.session_id,
            "knowledge_sessions": snapshot.knowledge.total_sessions,
            "regression_count": len(
                snapshot.regression.findings or snapshot.regression.regressions
            ),
            "advisor_observations": len(snapshot.advisor.observations),
            "comparison_included": snapshot.comparison is not None,
        }
        return sha256_v1(payload)

    @staticmethod
    def _generated_at(snapshot: _DecisionSnapshot) -> str:
        timestamps: List[str] = []
        for strategy in snapshot.knowledge.observed_launch_strategies:
            for ref in strategy.evidence_references:
                if ref.captured_at:
                    timestamps.append(ref.captured_at)
        for finding in snapshot.regression.findings or snapshot.regression.regressions:
            if finding.first_observed_at:
                timestamps.append(finding.first_observed_at)
        if snapshot.comparison is not None:
            timestamps.append(snapshot.comparison.generated_at)
        if timestamps:
            return sorted(timestamps)[-1]
        return "1970-01-01T00:00:00+00:00"

    @staticmethod
    def _notices(snapshot: _DecisionSnapshot) -> List[str]:
        notices = [
            "This plan is a read-only recommendation and does not authorize execution.",
            "All recommendations require explicit human approval before any execution step.",
        ]
        if snapshot.comparison is not None and snapshot.comparison.non_causality_notice:
            notices.append(snapshot.comparison.non_causality_notice)
        if snapshot.ask_summary:
            notices.append("Ask Alma context was included for operator review only.")
        refs = union_evidence_references(
            *(obs.evidence_references for obs in snapshot.advisor.observations)
        )
        if not refs:
            notices.append("Limited provenance available from upstream evidence layers.")
        return sorted(set(notices))
