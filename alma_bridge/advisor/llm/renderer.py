"""Optional bounded LLM rendering over deterministic advisor explanations."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Literal, Optional

from alma_bridge.advisor.llm.models import RenderedAdvisorExplanation
from alma_bridge.advisor.llm.provider import AdvisorLLMProvider, AdvisorLLMProviderError, NullAdvisorLLMProvider
from alma_bridge.advisor.llm.queries import build_llm_request, evidence_ids_for_observation
from alma_bridge.advisor.llm.validation import AdvisorOutputValidator, AdvisorValidationError
from alma_bridge.advisor.models import AdvisorExplanation, AdvisorObservation

RenderMode = Literal["deterministic", "llm", "deterministic_fallback"]


class OptionalLLMRenderer:
    """Rewrite deterministic advisor copy via an optional LLM provider."""

    def __init__(
        self,
        *,
        provider: AdvisorLLMProvider | None = None,
        validator: AdvisorOutputValidator | None = None,
        enabled: bool = False,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._provider = provider or NullAdvisorLLMProvider()
        self._validator = validator or AdvisorOutputValidator()
        self._enabled = enabled
        self._timeout_seconds = timeout_seconds
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="advisor-llm")

    def render(
        self,
        deterministic: AdvisorExplanation,
        *,
        mode: str = "deterministic",
    ) -> tuple[AdvisorExplanation, RenderMode, Optional[str]]:
        if mode != "llm" or not self._enabled:
            return deterministic, "deterministic", None

        try:
            request = build_llm_request(deterministic)
            response = self._call_provider(request)
            validated = self._validator.validate(deterministic, response.rendered)
            merged = self._merge(deterministic, validated)
            return merged, "llm", None
        except AdvisorValidationError as exc:
            return deterministic, "deterministic_fallback", exc.reason
        except AdvisorLLMProviderError:
            return deterministic, "deterministic_fallback", "provider_unavailable"
        except FuturesTimeoutError:
            return deterministic, "deterministic_fallback", "provider_timeout"
        except json.JSONDecodeError:
            return deterministic, "deterministic_fallback", "malformed_json"
        except Exception:
            return deterministic, "deterministic_fallback", "provider_error"

    def _call_provider(self, request):
        future = self._executor.submit(self._provider.generate, request)
        return future.result(timeout=self._timeout_seconds)

    @staticmethod
    def _merge(
        deterministic: AdvisorExplanation,
        rendered: RenderedAdvisorExplanation,
    ) -> AdvisorExplanation:
        rendered_by_id = {obs.observation_id: obs for obs in rendered.observations}
        merged_observations: list[AdvisorObservation] = []
        for source in deterministic.observations:
            rendered_obs = rendered_by_id[source.observation_id]
            merged_observations.append(
                source.model_copy(update={"statement": rendered_obs.statement})
            )
        return deterministic.model_copy(
            update={
                "summary": rendered.summary,
                "limitations": sorted(set(rendered.limitations or deterministic.limitations)),
                "observations": merged_observations,
            }
        )
