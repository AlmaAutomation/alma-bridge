"""Built-in conformance scenarios."""

from __future__ import annotations

from pathlib import Path
from typing import List

from alma_bridge.runtime.conformance.models import ConformanceScenario

_FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "native_runtime" / "bin"

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
        title="Native Alma candidate must fail closed when disabled",
        baseline_provider_id="wine",
        candidate_provider_id="native_alma",
        file_path="",
        required_signals=["candidate_error"],
    ),
    ConformanceScenario(
        scenario_id="native_vs_wine_hello64",
        title="Native Alma vs Wine hello64 fixture",
        baseline_provider_id="wine",
        candidate_provider_id="native_alma",
        file_path=str(_FIXTURES / "hello64.exe"),
        required_signals=["exit_code", "stdout"],
    ),
]


def list_scenarios() -> List[ConformanceScenario]:
    return list(DEFAULT_SCENARIOS)
