"""Ask Alma service facade."""

from __future__ import annotations

from alma_bridge.ask.answer import DeterministicAnswerBuilder, NullAskLLMProvider, OptionalLLMAnswerRenderer
from alma_bridge.ask.classifier import QuestionClassifier
from alma_bridge.ask.context import AskAlmaContextBuilder
from alma_bridge.ask.models import AskAlmaAnswer, AskAlmaContext, AskAlmaQuestion, QuestionType
from alma_bridge.config import settings


class AskAlmaService:
    """Evidence-grounded compatibility Q&A."""

    def __init__(
        self,
        *,
        classifier: QuestionClassifier | None = None,
        context_builder: AskAlmaContextBuilder | None = None,
        answer_builder: DeterministicAnswerBuilder | None = None,
        llm_renderer: OptionalLLMAnswerRenderer | None = None,
    ) -> None:
        self._classifier = classifier or QuestionClassifier()
        self._context_builder = context_builder or AskAlmaContextBuilder()
        self._answer_builder = answer_builder or DeterministicAnswerBuilder()
        self._llm_renderer = llm_renderer or OptionalLLMAnswerRenderer(
            provider=NullAskLLMProvider(),
            enabled=settings.advisor_llm_enabled,
            timeout_seconds=settings.advisor_llm_timeout_seconds,
        )

    def ask(self, payload: AskAlmaQuestion) -> AskAlmaAnswer:
        classification = self._classifier.classify(payload.question)
        if classification.question_type == QuestionType.UNSUPPORTED:
            context = AskAlmaContext(
                application_fingerprint=payload.application_fingerprint,
                application_name=payload.application_fingerprint,
                session_id=payload.session_id,
                question_type=QuestionType.UNSUPPORTED,
            )
            deterministic = self._answer_builder.build(question=payload.question, context=context)
            return self._finalize(deterministic, render=payload.render)

        context = self._context_builder.build(
            fingerprint=payload.application_fingerprint,
            session_id=payload.session_id,
            question_type=classification.question_type,
        )
        deterministic = self._answer_builder.build(question=payload.question, context=context)
        return self._finalize(deterministic, render=payload.render)

    def _finalize(self, deterministic: AskAlmaAnswer, *, render: str) -> AskAlmaAnswer:
        answer, render_mode, fallback_reason = self._llm_renderer.render(
            deterministic,
            mode=render,
        )
        return answer.model_copy(
            update={
                "render_mode": render_mode,
                "fallback_reason": fallback_reason,
            }
        )
