"""Build Ask Alma context from minimal read-only evidence fetches."""

from __future__ import annotations

from typing import Optional

from alma_bridge.advisor.models import AdvisorNotFoundError as AdvisorServiceNotFoundError
from alma_bridge.advisor.service import CompatibilityAdvisorService
from alma_bridge.ask.evidence_query import EvidenceQueryPlanner
from alma_bridge.ask.models import AskAlmaContext, AskAlmaNotFoundError, QuestionType
from alma_bridge.knowledge.models import KnowledgeNotFoundError
from alma_bridge.knowledge.service import CompatibilityKnowledgeService
from alma_bridge.regression.models import RegressionNotFoundError
from alma_bridge.regression.service import CompatibilityRegressionService


class AskAlmaContextBuilder:
    """Fetch only the evidence layers required for a question class."""

    def __init__(
        self,
        *,
        knowledge_service: CompatibilityKnowledgeService | None = None,
        regression_service: CompatibilityRegressionService | None = None,
        advisor_service: CompatibilityAdvisorService | None = None,
    ) -> None:
        self._knowledge = knowledge_service or CompatibilityKnowledgeService()
        self._regression = regression_service or CompatibilityRegressionService()
        self._advisor = advisor_service or CompatibilityAdvisorService()

    def build(
        self,
        *,
        fingerprint: str,
        session_id: Optional[str],
        question_type: QuestionType,
    ) -> AskAlmaContext:
        plan = EvidenceQueryPlanner().plan(question_type)
        knowledge_profile = None
        regression_report = None
        advisor_explanation = None
        application_name = fingerprint

        if "knowledge" in plan.services:
            try:
                profile = self._knowledge.profile_for_application(fingerprint)
            except KnowledgeNotFoundError as exc:
                raise AskAlmaNotFoundError(str(exc)) from exc
            knowledge_profile = profile.model_dump(mode="json")
            application_name = profile.application_name

        if "regression" in plan.services:
            try:
                if session_id:
                    report = self._regression.report_for_session(session_id)
                else:
                    report = self._regression.report_for_application(fingerprint)
            except RegressionNotFoundError as exc:
                raise AskAlmaNotFoundError(str(exc)) from exc
            regression_report = report.model_dump(mode="json")
            application_name = report.application_name

        if "advisor" in plan.services:
            try:
                explanation = self._advisor.explain_for_application(
                    fingerprint,
                    session_id=session_id,
                    render="deterministic",
                )
            except AdvisorServiceNotFoundError as exc:
                raise AskAlmaNotFoundError(str(exc)) from exc
            advisor_explanation = explanation.model_dump(mode="json")
            application_name = explanation.application_name

        return AskAlmaContext(
            application_fingerprint=fingerprint,
            application_name=application_name,
            session_id=session_id,
            question_type=question_type,
            knowledge_profile=knowledge_profile,
            regression_report=regression_report,
            advisor_explanation=advisor_explanation,
        )
