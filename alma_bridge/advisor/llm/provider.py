"""LLM provider protocol and built-in no-op provider."""

from __future__ import annotations

import json
from typing import Protocol, runtime_checkable

from alma_bridge.advisor.llm.models import AdvisorLLMRequest, AdvisorLLMResponse, RenderedAdvisorExplanation


class AdvisorLLMProviderError(Exception):
    """Raised when an LLM provider cannot produce a response."""


@runtime_checkable
class AdvisorLLMProvider(Protocol):
    def generate(self, request: AdvisorLLMRequest) -> AdvisorLLMResponse:
        ...


class NullAdvisorLLMProvider:
    """Default provider that never calls external services."""

    def generate(self, request: AdvisorLLMRequest) -> AdvisorLLMResponse:
        raise AdvisorLLMProviderError("advisor LLM provider is not configured")


class JsonAdvisorLLMProvider:
    """Test/dummy provider that returns pre-serialized rendered JSON."""

    def __init__(self, payload: dict | str) -> None:
        self._payload = payload

    def generate(self, request: AdvisorLLMRequest) -> AdvisorLLMResponse:
        if isinstance(self._payload, str):
            parsed = json.loads(self._payload)
        else:
            parsed = self._payload
        rendered = RenderedAdvisorExplanation.model_validate(parsed)
        return AdvisorLLMResponse(rendered=rendered, raw_text=json.dumps(parsed))


class TimeoutAdvisorLLMProvider:
    """Test provider that simulates a hung LLM call."""

    def generate(self, request: AdvisorLLMRequest) -> AdvisorLLMResponse:
        import time

        time.sleep(60)
        raise AdvisorLLMProviderError("timeout simulation")


class ExceptionAdvisorLLMProvider:
    """Test provider that raises unexpectedly."""

    def generate(self, request: AdvisorLLMRequest) -> AdvisorLLMResponse:
        raise RuntimeError("provider exploded")


def build_advisor_llm_provider(*, enabled: bool, provider_name: str) -> AdvisorLLMProvider:
    """Construct configured advisor LLM provider without vendor SDK coupling."""
    if not enabled:
        return NullAdvisorLLMProvider()
    # Phase 2: external vendor providers are wired in later phases.
    _ = provider_name
    return NullAdvisorLLMProvider()
