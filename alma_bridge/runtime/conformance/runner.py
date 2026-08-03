"""Conformance run orchestration (non-authoritative)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from alma_bridge.config import settings
from alma_bridge.runtime.conformance.comparison import classify_baseline_comparison
from alma_bridge.runtime.conformance.models import (
    ConformanceClassification,
    ConformanceRunResult,
    ConformanceScenario,
)
from alma_bridge.runtime.errors import RuntimeNotSupportedError
from alma_bridge.runtime.registry import RuntimeRegistry


class ConformanceRunner:
    """Execute inspect/prepare and optional launch conformance checks."""

    def __init__(self, registry: RuntimeRegistry) -> None:
        self._registry = registry

    def run_scenario(
        self,
        scenario: ConformanceScenario,
        *,
        file_path: Optional[str] = None,
        launch: bool = False,
    ) -> ConformanceRunResult:
        target = file_path or scenario.file_path
        baseline_provider = self._registry.get(scenario.baseline_provider_id)
        candidate_provider = self._registry.get(scenario.candidate_provider_id)

        baseline_evidence: Dict[str, Any] = {}
        candidate_evidence: Dict[str, Any] = {}
        notes: List[str] = []

        if target and not Path(target).is_file():
            notes.append(f"file not found: {target}")
            target = ""

        if target:
            baseline_evidence = self._provider_evidence(
                baseline_provider, target, launch=launch and scenario.baseline_provider_id != "native_alma"
            )
            try:
                candidate_evidence = self._provider_evidence(
                    candidate_provider, target, launch=launch or scenario.candidate_provider_id == "native_alma"
                )
            except RuntimeNotSupportedError as exc:
                candidate_evidence = {
                    "failed": True,
                    "error": str(exc),
                    "candidate_error": True,
                }
        else:
            notes.append("no file_path supplied; classification uses structural signals only")
            if scenario.candidate_provider_id == "native_alma" and not (
                settings.native_runtime_enabled and settings.allow_experimental_runtimes
            ):
                candidate_evidence["candidate_error"] = True
                candidate_evidence["failed"] = True

        classification = classify_baseline_comparison(
            baseline=baseline_evidence,
            candidate=candidate_evidence,
            required_signals=scenario.required_signals,
        )
        return ConformanceRunResult(
            scenario_id=scenario.scenario_id,
            baseline_provider_id=scenario.baseline_provider_id,
            candidate_provider_id=scenario.candidate_provider_id,
            classification=classification,
            notes=notes,
            baseline_evidence=baseline_evidence,
            candidate_evidence=candidate_evidence,
        )

    def _provider_evidence(self, provider, target: str, *, launch: bool) -> Dict[str, Any]:
        evidence: Dict[str, Any] = {}
        inspection = provider.inspect(target)
        evidence["ready"] = inspection.ready
        evidence["binary_format"] = inspection.binary_format
        try:
            prepared = provider.prepare(target)
            evidence["exit_code"] = 0 if prepared.ready else 1
            evidence["command"] = prepared.command
            if launch and prepared.ready and getattr(provider, "provider_id", "") == "native_alma":
                if settings.native_runtime_enabled and settings.allow_experimental_runtimes:
                    handle = provider.launch(target)
                    observation = provider.observe(handle)
                    provider.teardown(handle)
                    evidence["exit_code"] = observation.exit_code
                    evidence["stdout"] = observation.stdout
                    evidence["stderr"] = observation.stderr
        except RuntimeNotSupportedError:
            raise
        except Exception as exc:
            evidence["failed"] = True
            evidence["error"] = str(exc)
        return evidence
