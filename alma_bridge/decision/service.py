"""Public service facade for the read-only Decision Engine."""

from __future__ import annotations

from typing import Optional

from alma_bridge.advisor.models import AdvisorNotFoundError
from alma_bridge.decision.engine import DecisionEngine
from alma_bridge.decision.errors import DecisionNotFoundError, MalformedDecisionEvidenceError
from alma_bridge.decision.models import DecisionInput, DecisionPlan
from alma_bridge.regression.models import RegressionNotFoundError


class DecisionService:
    """Read-only execution plan recommendations from composed evidence layers."""

    def __init__(self, engine: DecisionEngine | None = None) -> None:
        self._engine = engine or DecisionEngine()

    def plan_for_session(
        self,
        session_id: str,
        *,
        baseline_session_id: Optional[str] = None,
        comparison_session_id: Optional[str] = None,
        ask_question: Optional[str] = None,
    ) -> DecisionPlan:
        return self.plan_from_input(
            DecisionInput(
                session_id=session_id,
                baseline_session_id=baseline_session_id,
                comparison_session_id=comparison_session_id,
                ask_question=ask_question,
            )
        )

    def plan_for_application(
        self,
        application_fingerprint: str,
        *,
        session_id: Optional[str] = None,
        baseline_session_id: Optional[str] = None,
        comparison_session_id: Optional[str] = None,
        ask_question: Optional[str] = None,
    ) -> DecisionPlan:
        return self.plan_from_input(
            DecisionInput(
                application_fingerprint=application_fingerprint,
                session_id=session_id,
                baseline_session_id=baseline_session_id,
                comparison_session_id=comparison_session_id,
                ask_question=ask_question,
            )
        )

    def plan_from_input(self, decision_input: DecisionInput) -> DecisionPlan:
        try:
            return self._engine.build_plan(decision_input)
        except RegressionNotFoundError as exc:
            raise DecisionNotFoundError(str(exc)) from exc
        except AdvisorNotFoundError as exc:
            raise DecisionNotFoundError(str(exc)) from exc
        except MalformedDecisionEvidenceError:
            raise
