"""Conformance run orchestration (non-authoritative)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from alma_bridge.runtime.conformance.comparison import classify_baseline_comparison
from alma_bridge.runtime.conformance.models import (
    ConformanceClassification,
    ConformanceRunResult,
    ConformanceScenario,
)
from alma_bridge.runtime.errors import RuntimeNotSupportedError
from alma_bridge.runtime.registry import RuntimeRegistry


class ConformanceRunner:
    """Execute inspect/prepare-only conformance checks for Phase 0B."""

    def __init__(self, registry: RuntimeRegistry) -> None:
        self._registry = registry

    def run_scenario(
        self,
        scenario: ConformanceScenario,
        *,
        file_path: Optional[str] = None,
    ) -> ConformanceRunResult:
        target = file_path or scenario.file_path
        baseline_provider = self._registry.get(scenario.baseline_provider_id)
        candidate_provider = self._registry.get(scenario.candidate_provider_id)

        baseline_evidence: Dict[str, Any] = {}
        candidate_evidence: Dict[str, Any] = {}
        notes: List[str] = []

        if target:
            baseline_inspection = baseline_provider.inspect(target)
            baseline_evidence = {
                "ready": baseline_inspection.ready,
                "binary_format": baseline_inspection.binary_format,
            }
            try:
                baseline_prepare = baseline_provider.prepare(target)
                baseline_evidence["exit_code"] = 0 if baseline_prepare.ready else 1
                baseline_evidence["command"] = baseline_prepare.command
            except Exception as exc:
                baseline_evidence["failed"] = True
                baseline_evidence["error"] = str(exc)

            try:
                candidate_inspection = candidate_provider.inspect(target)
                candidate_evidence["ready"] = candidate_inspection.ready
                candidate_prepare = candidate_provider.prepare(target)
                candidate_evidence["exit_code"] = 0 if candidate_prepare.ready else 1
                candidate_evidence["command"] = candidate_prepare.command
            except RuntimeNotSupportedError as exc:
                candidate_evidence["failed"] = True
                candidate_evidence["error"] = str(exc)
                candidate_evidence["candidate_error"] = True
            except Exception as exc:
                candidate_evidence["failed"] = True
                candidate_evidence["error"] = str(exc)
        else:
            notes.append("no file_path supplied; classification uses structural signals only")
            if scenario.candidate_provider_id == "native_alma":
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
