"""Built-in conformance scenarios for Phase 0B."""

from __future__ import annotations

from typing import List

from alma_bridge.runtime.conformance.models import ConformanceScenario

DEFAULT_SCENARIOS: List[ConformanceScenario] = [
    ConformanceScenario(
        scenario_id="wine_vs_proton_pe_console",
        title="Wine vs Proton PE console baseline",
        baseline_provider_id="wine",
        candidate_provider_id="proton",
        file_path="",
        required_signals=["exit_code", "stdout"],
    ),
    ConformanceScenario(
        scenario_id="container_vs_wine_pe",
        title="Container vs Wine PE isolation",
        baseline_provider_id="wine",
        candidate_provider_id="container",
        file_path="",
        required_signals=["exit_code"],
    ),
    ConformanceScenario(
        scenario_id="native_alma_fail_closed",
        title="Native Alma candidate must fail closed",
        baseline_provider_id="wine",
        candidate_provider_id="native_alma",
        file_path="",
        required_signals=["candidate_error"],
    ),
]


def list_scenarios() -> List[ConformanceScenario]:
    return list(DEFAULT_SCENARIOS)
