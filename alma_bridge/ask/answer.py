"""Deterministic and optional LLM answer generation for Ask Alma."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import List, Optional, Protocol, Tuple, runtime_checkable

from alma_bridge.advisor.policy import validate_statement
from alma_bridge.ask.models import (
    ASK_ENGINE_VERSION,
    ASK_SCHEMA_VERSION,
    AskAlmaAnswer,
    AskAlmaContext,
    AskAlmaEvidenceReference,
    QuestionType,
)
from alma_bridge.ask.policy import validate_answer
from alma_bridge.ask.queries import merge_evidence_references, refs_from_knowledge, to_ask_evidence_reference
from alma_bridge.knowledge.models import CompatibilityKnowledgeProfile


class DeterministicAnswerBuilder:
    """Produce factual template answers from AskAlmaContext."""

    def build(self, *, question: str, context: AskAlmaContext) -> AskAlmaAnswer:
        profile = self._profile(context)
        handlers = {
            QuestionType.COMPATIBILITY_SUMMARY: self._compatibility_summary,
            QuestionType.VERIFICATION_HISTORY: self._verification_history,
            QuestionType.FRAMEWORK_HISTORY: self._framework_history,
            QuestionType.LAUNCH_STRATEGY_HISTORY: self._launch_strategy_history,
            QuestionType.RUNTIME_OBSERVATIONS: self._runtime_observations,
            QuestionType.REGRESSION_CHANGES: self._regression_changes,
            QuestionType.CONFLICTING_EVIDENCE: self._conflicting_evidence,
            QuestionType.EVIDENCE_PROVENANCE: self._evidence_provenance,
            QuestionType.REMEDIATION_REFUSAL: self._remediation_refusal,
            QuestionType.STRATEGY_RECOMMENDATION_REFUSAL: self._strategy_refusal,
            QuestionType.UNSUPPORTED: self._unsupported,
        }
        handler = handlers.get(context.question_type, self._unsupported)
        answer, confidence, refs, limitations = handler(question, context, profile)
        result = AskAlmaAnswer(
            question=question,
            question_type=context.question_type,
            answer=answer,
            confidence=confidence,
            evidence_references=refs,
            limitations=limitations,
            schema_version=ASK_SCHEMA_VERSION,
            engine_version=ASK_ENGINE_VERSION,
        )
        validate_answer(result)
        return result

    @staticmethod
    def _profile(context: AskAlmaContext) -> CompatibilityKnowledgeProfile | None:
        if not context.knowledge_profile:
            return None
        return CompatibilityKnowledgeProfile.model_validate(context.knowledge_profile)

    def _verification_history(
        self,
        question: str,
        context: AskAlmaContext,
        profile: CompatibilityKnowledgeProfile | None,
    ) -> Tuple[str, float, List[AskAlmaEvidenceReference], List[str]]:
        if not profile:
            return self._insufficient(question, context)
        refs = refs_from_knowledge(profile, limit=8)
        if profile.verified_successes:
            answer = (
                f"Yes. {context.application_name} has {profile.verified_successes} "
                f"authoritatively verified successful session(s) across {profile.total_sessions} observed session(s)."
            )
            confidence = min(1.0, 0.6 + 0.1 * profile.verified_successes)
        elif profile.verified_failures:
            answer = (
                f"No authoritative verified successes are recorded. "
                f"{profile.verified_failures} session(s) had authoritative verified failure."
            )
            confidence = 0.8
        else:
            answer = (
                f"No authoritative verified successes are recorded for {context.application_name}. "
                f"{profile.unverifiable_sessions} session(s) were unverifiable."
            )
            confidence = 0.5
        return answer, confidence, refs, [
            "Alma does not infer a runtime requirement from these observations."
        ]

    def _launch_strategy_history(
        self,
        question: str,
        context: AskAlmaContext,
        profile: CompatibilityKnowledgeProfile | None,
    ) -> Tuple[str, float, List[AskAlmaEvidenceReference], List[str]]:
        if not profile or not profile.observed_launch_strategies:
            return self._insufficient(question, context)
        strategy_name = self._extract_strategy_name(question) or profile.observed_launch_strategies[0].strategy
        match = next(
            (item for item in profile.observed_launch_strategies if item.strategy == strategy_name),
            profile.observed_launch_strategies[0],
        )
        refs = [
            to_ask_evidence_reference(ref, source_layer="knowledge")
            for ref in match.evidence_references
        ]
        if match.verified_successes:
            prefix = "Yes. "
        else:
            prefix = "No authoritative verified successes recorded. "
        answer = (
            f"{prefix}{match.strategy} has {match.verified_successes} authoritative verified success(es) "
            f"and {match.verified_failures} authoritative verified failure(s) across "
            f"{match.attempts} observed attempt(s) ({match.success_rate:.0%} verified success rate)."
        )
        return answer, min(1.0, match.success_rate + 0.1), refs, [
            "Alma can show observed strategy outcomes but does not recommend execution strategies in this phase.",
        ]

    def _framework_history(
        self,
        question: str,
        context: AskAlmaContext,
        profile: CompatibilityKnowledgeProfile | None,
    ) -> Tuple[str, float, List[AskAlmaEvidenceReference], List[str]]:
        if not profile or not profile.observed_frameworks:
            return self._insufficient(question, context)
        names = ", ".join(item.framework for item in profile.observed_frameworks)
        refs = refs_from_knowledge(profile, limit=8)
        answer = f"Alma has observed the following frameworks for {context.application_name}: {names}."
        return answer, 0.85, refs, []

    def _runtime_observations(
        self,
        question: str,
        context: AskAlmaContext,
        profile: CompatibilityKnowledgeProfile | None,
    ) -> Tuple[str, float, List[AskAlmaEvidenceReference], List[str]]:
        if not profile or not profile.observed_runtimes:
            return self._insufficient(question, context)
        parts = [
            f"{item.runtime} observed in {item.observation_count} session(s) "
            f"({item.verified_success_observation_count} in verified sessions)"
            for item in profile.observed_runtimes
        ]
        refs = [
            to_ask_evidence_reference(ref, source_layer="knowledge")
            for runtime in profile.observed_runtimes
            for ref in runtime.evidence_references
        ]
        answer = f"Observed runtimes for {context.application_name}: " + "; ".join(parts) + "."
        limitations = ["Alma does not infer installation requirements from runtime observations."]
        return answer, 0.8, merge_evidence_references(refs), limitations

    def _regression_changes(
        self,
        question: str,
        context: AskAlmaContext,
        profile: CompatibilityKnowledgeProfile | None,
    ) -> Tuple[str, float, List[AskAlmaEvidenceReference], List[str]]:
        report = context.regression_report or {}
        findings = report.get("findings") or report.get("regressions") or []
        refs: List[AskAlmaEvidenceReference] = []
        for finding in findings:
            for ref in finding.get("evidence_references") or []:
                refs.append(
                    AskAlmaEvidenceReference(
                        source_layer="regression",
                        source_type=ref["source_type"],
                        source_id=ref["source_id"],
                        session_id=ref.get("session_id"),
                        attempt_id=ref.get("attempt_id"),
                        artifact_key=ref.get("artifact_key") or "",
                    )
                )
        if findings:
            primary = findings[0]
            answer = primary.get("summary") or (
                "The comparison session recorded a compatibility change relative to the baseline."
            )
            return answer, float(primary.get("confidence") or 0.8), merge_evidence_references(refs), []
        unchanged = report.get("unchanged_summary") or (
            "No compatibility regressions were detected relative to the available baseline."
        )
        if profile:
            refs = refs_from_knowledge(profile, limit=4)
        return unchanged, 0.6, refs, []

    def _conflicting_evidence(
        self,
        question: str,
        context: AskAlmaContext,
        profile: CompatibilityKnowledgeProfile | None,
    ) -> Tuple[str, float, List[AskAlmaEvidenceReference], List[str]]:
        if not profile or not profile.conflicts:
            return (
                f"No conflicting framework evidence is recorded for {context.application_name}.",
                0.7,
                refs_from_knowledge(profile, limit=4) if profile else [],
                [],
            )
        conflict = profile.conflicts[0]
        sides = " and ".join(conflict.competing_observations)
        refs = [
            to_ask_evidence_reference(ref, source_layer="knowledge")
            for side_refs in conflict.evidence_by_side.values()
            for ref in side_refs
        ]
        answer = f"Conflicting framework evidence is recorded: {sides} have both been observed."
        return answer, 0.85, merge_evidence_references(refs), [
            "No framework is selected as authoritative."
        ]

    def _evidence_provenance(
        self,
        question: str,
        context: AskAlmaContext,
        profile: CompatibilityKnowledgeProfile | None,
    ) -> Tuple[str, float, List[AskAlmaEvidenceReference], List[str]]:
        if not profile:
            return self._insufficient(question, context)
        target = self._extract_framework_name(question)
        if target:
            framework = next(
                (item for item in profile.observed_frameworks if item.framework.lower() == target.lower()),
                None,
            )
            if framework:
                refs = [
                    to_ask_evidence_reference(ref, source_layer="knowledge")
                    for ref in framework.evidence_references
                ]
                answer = (
                    f"{framework.framework} detections are supported by {len(refs)} evidence reference(s) "
                    f"across {framework.observation_count} observed session(s)."
                )
                return answer, framework.confidence, refs, []
        refs = refs_from_knowledge(profile, limit=12)
        answer = (
            f"Alma recorded {len(refs)} evidence reference(s) supporting compatibility observations "
            f"for {context.application_name}."
        )
        return answer, 0.75, refs, []

    def _compatibility_summary(
        self,
        question: str,
        context: AskAlmaContext,
        profile: CompatibilityKnowledgeProfile | None,
    ) -> Tuple[str, float, List[AskAlmaEvidenceReference], List[str]]:
        if context.advisor_explanation:
            explanation = context.advisor_explanation
            refs = [
                AskAlmaEvidenceReference(
                    source_layer="advisor",
                    source_type=ref["source_type"],
                    source_id=ref["source_id"],
                    session_id=ref.get("session_id"),
                    attempt_id=ref.get("attempt_id"),
                    artifact_key=ref.get("artifact_key") or "",
                )
                for obs in explanation.get("observations") or []
                for ref in obs.get("evidence_references") or []
            ]
            return explanation.get("summary") or "Compatibility summary unavailable.", 0.8, merge_evidence_references(refs), list(
                explanation.get("limitations") or []
            )
        if profile:
            return self._verification_history(question, context, profile)
        return self._insufficient(question, context)

    def _remediation_refusal(
        self,
        question: str,
        context: AskAlmaContext,
        profile: CompatibilityKnowledgeProfile | None,
    ) -> Tuple[str, float, List[AskAlmaEvidenceReference], List[str]]:
        refs = refs_from_knowledge(profile, limit=6) if profile else []
        if profile and profile.observed_runtimes:
            runtime = profile.observed_runtimes[0]
            answer = (
                f"Ask Alma is read-only and cannot execute remediation. "
                f"Alma has observed {runtime.runtime} runtime evidence in "
                f"{runtime.observation_count} session(s) but does not infer installation requirements."
            )
        else:
            answer = (
                "Ask Alma is read-only and cannot execute remediation or install dependencies in this phase."
            )
        return answer, 0.9, refs, [
            "Alma does not infer installation requirements from runtime observations."
        ]

    def _strategy_refusal(
        self,
        question: str,
        context: AskAlmaContext,
        profile: CompatibilityKnowledgeProfile | None,
    ) -> Tuple[str, float, List[AskAlmaEvidenceReference], List[str]]:
        refs = refs_from_knowledge(profile, limit=6) if profile else []
        answer = (
            "Alma can show observed strategy outcomes but does not recommend execution strategies in this phase."
        )
        if profile and profile.observed_launch_strategies:
            strategy = profile.observed_launch_strategies[0]
            answer += (
                f" {strategy.strategy} has {strategy.verified_successes} authoritative verified success(es) "
                f"across {strategy.attempts} observed attempt(s)."
            )
        return answer, 0.9, refs, []

    def _unsupported(
        self,
        question: str,
        context: AskAlmaContext,
        profile: CompatibilityKnowledgeProfile | None,
    ) -> Tuple[str, float, List[AskAlmaEvidenceReference], List[str]]:
        return (
            "This question is not supported in Ask Alma Phase 1. "
            "Try asking about verification history, frameworks, launch strategies, runtime observations, "
            "regression changes, or conflicting evidence.",
            0.2,
            [],
            ["Unsupported question class."],
        )

    def _insufficient(
        self,
        question: str,
        context: AskAlmaContext,
    ) -> Tuple[str, float, List[AskAlmaEvidenceReference], List[str]]:
        return (
            f"Evidence is insufficient to answer this question reliably for {context.application_name}.",
            0.2,
            [],
            ["Insufficient evidence."],
        )

    @staticmethod
    def _extract_strategy_name(question: str) -> str | None:
        match = re.search(r"\b(wine_gui|proton|native|container)\b", question.lower())
        return match.group(1) if match else None

    @staticmethod
    def _extract_framework_name(question: str) -> str | None:
        match = re.search(r"\b(wxwidgets|qt|electron|gtk|flutter)\b", question.lower())
        return match.group(1) if match else None


class AskLLMProviderError(Exception):
    """Raised when Ask Alma LLM rewrite is unavailable."""


@runtime_checkable
class AskLLMProvider(Protocol):
    def rewrite_answer(
        self,
        *,
        question: str,
        deterministic_answer: str,
        limitations: List[str],
    ) -> str:
        ...


class NullAskLLMProvider:
    def rewrite_answer(self, *, question: str, deterministic_answer: str, limitations: List[str]) -> str:
        raise AskLLMProviderError("ask llm provider is not configured")


class JsonAskLLMProvider:
    def __init__(self, answer: str) -> None:
        self._answer = answer

    def rewrite_answer(self, *, question: str, deterministic_answer: str, limitations: List[str]) -> str:
        return self._answer


class OptionalLLMAnswerRenderer:
    """Optional bounded rewrite of deterministic Ask Alma answers."""

    def __init__(
        self,
        *,
        provider: AskLLMProvider | None = None,
        enabled: bool = False,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._provider = provider or NullAskLLMProvider()
        self._enabled = enabled
        self._timeout_seconds = timeout_seconds
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ask-llm")

    def render(
        self,
        deterministic: AskAlmaAnswer,
        *,
        mode: str = "deterministic",
    ) -> Tuple[AskAlmaAnswer, str, Optional[str]]:
        if mode != "llm" or not self._enabled:
            return deterministic, "deterministic", None
        try:
            future = self._executor.submit(
                self._provider.rewrite_answer,
                question=deterministic.question,
                deterministic_answer=deterministic.answer,
                limitations=list(deterministic.limitations),
            )
            rewritten = future.result(timeout=self._timeout_seconds)
            candidate = deterministic.model_copy(update={"answer": rewritten})
            validate_answer(candidate)
            if self._introduced_new_claims(deterministic.answer, rewritten):
                raise ValueError("new claims introduced")
            return candidate, "llm", None
        except AskLLMProviderError:
            return deterministic, "deterministic_fallback", "provider_unavailable"
        except FuturesTimeoutError:
            return deterministic, "deterministic_fallback", "provider_timeout"
        except Exception:
            return deterministic, "deterministic_fallback", "validation_failed"

    @staticmethod
    def _introduced_new_claims(before: str, after: str) -> bool:
        framework_pattern = re.compile(r"\b(qt|wxwidgets|electron|gtk|flutter)\b", re.IGNORECASE)
        before_set = {m.lower() for m in framework_pattern.findall(before)}
        after_set = {m.lower() for m in framework_pattern.findall(after)}
        if after_set - before_set:
            return True
        return bool(validate_statement(after))
