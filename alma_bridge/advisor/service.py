"""Compatibility Advisor service facade — read-only deterministic explanations."""

from __future__ import annotations

from typing import Literal, Optional

from alma_bridge.advisor.context import AdvisorContextBuilder
from alma_bridge.advisor.explanation import DeterministicAdvisorEngine
from alma_bridge.advisor.llm.provider import AdvisorLLMProvider, build_advisor_llm_provider
from alma_bridge.advisor.llm.renderer import OptionalLLMRenderer
from alma_bridge.advisor.models import (
    AdvisorExplanation,
    AdvisorExplanationResponse,
    AdvisorNotFoundError,
    MalformedAdvisorError,
    PolicyViolationError,
)
from alma_bridge.config import settings
from alma_bridge.regression.models import RegressionNotFoundError
from alma_bridge.regression.repository import ReadOnlyRegressionEvidenceAdapter

RenderParam = Literal["deterministic", "llm"]


class CompatibilityAdvisorService:
    """Read-only advisor explanations composed from knowledge and regression layers."""

    def __init__(
        self,
        context_builder: AdvisorContextBuilder | None = None,
        engine: DeterministicAdvisorEngine | None = None,
        llm_renderer: OptionalLLMRenderer | None = None,
        llm_provider: AdvisorLLMProvider | None = None,
    ) -> None:
        self._context_builder = context_builder or AdvisorContextBuilder()
        self._engine = engine or DeterministicAdvisorEngine()
        self._repository = ReadOnlyRegressionEvidenceAdapter()
        provider = llm_provider or build_advisor_llm_provider(
            enabled=settings.advisor_llm_enabled,
            provider_name=settings.advisor_llm_provider,
        )
        self._llm_renderer = llm_renderer or OptionalLLMRenderer(
            provider=provider,
            enabled=settings.advisor_llm_enabled,
            timeout_seconds=settings.advisor_llm_timeout_seconds,
        )

    def explain_for_application(
        self,
        fingerprint: str,
        *,
        session_id: Optional[str] = None,
        render: RenderParam = "deterministic",
    ) -> AdvisorExplanationResponse:
        deterministic = self._deterministic_explanation(fingerprint, session_id=session_id)
        return self._maybe_render(deterministic, render=render)

    def explain_for_session(
        self,
        session_id: str,
        *,
        render: RenderParam = "deterministic",
    ) -> AdvisorExplanationResponse:
        session = self._repository.get_session_record(session_id)
        if not session:
            raise AdvisorNotFoundError(f"no session evidence for {session_id}")
        fingerprint = str(session.get("file_hash") or "")
        if not fingerprint:
            raise AdvisorNotFoundError(f"session {session_id} has no application fingerprint")
        return self.explain_for_application(fingerprint, session_id=session_id, render=render)

    def _deterministic_explanation(
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

    def _maybe_render(
        self,
        deterministic: AdvisorExplanation,
        *,
        render: RenderParam,
    ) -> AdvisorExplanationResponse:
        explanation, render_mode, fallback_reason = self._llm_renderer.render(
            deterministic,
            mode=render,
        )
        return AdvisorExplanationResponse(
            **explanation.model_dump(),
            render_mode=render_mode,
            fallback_reason=fallback_reason,
        )
