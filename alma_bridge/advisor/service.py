"""Compatibility Advisor service facade — read-only deterministic explanations."""

from __future__ import annotations

from typing import Optional

from alma_bridge.advisor.context import AdvisorContextBuilder
from alma_bridge.advisor.explanation import DeterministicAdvisorEngine
from alma_bridge.advisor.models import (
    AdvisorExplanation,
    AdvisorNotFoundError,
    MalformedAdvisorError,
    PolicyViolationError,
)
from alma_bridge.regression.models import RegressionNotFoundError
from alma_bridge.regression.repository import ReadOnlyRegressionEvidenceAdapter


class CompatibilityAdvisorService:
    """Read-only advisor explanations composed from knowledge and regression layers."""

    def __init__(
        self,
        context_builder: AdvisorContextBuilder | None = None,
        engine: DeterministicAdvisorEngine | None = None,
    ) -> None:
        self._context_builder = context_builder or AdvisorContextBuilder()
        self._engine = engine or DeterministicAdvisorEngine()
        self._repository = ReadOnlyRegressionEvidenceAdapter()

    def explain_for_application(
        self,
        fingerprint: str,
        *,
        session_id: Optional[str] = None,
    ) -> AdvisorExplanation:
        try:
            context = self._context_builder.build(fingerprint, session_id=session_id)
        except RegressionNotFoundError as exc:
            raise AdvisorNotFoundError(str(exc)) from exc
        except MalformedAdvisorError:
            raise
        try:
            return self._engine.explain(context)
        except PolicyViolationError:
            raise

    def explain_for_session(self, session_id: str) -> AdvisorExplanation:
        session = self._repository.get_session_record(session_id)
        if not session:
            raise AdvisorNotFoundError(f"no session evidence for {session_id}")
        fingerprint = str(session.get("file_hash") or "")
        if not fingerprint:
            raise AdvisorNotFoundError(f"session {session_id} has no application fingerprint")
        return self.explain_for_application(fingerprint, session_id=session_id)
