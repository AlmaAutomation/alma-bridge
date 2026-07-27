#!/usr/bin/env python3
"""Binary search collected pytest order for minimal polluter of each victim."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORDER_FILE = Path("/tmp/pytest-order.txt")

VICTIMS = [
    "tests/test_orchestrator_retries.py::test_orchestrator_applies_preferred_remediation_first",
    "tests/test_orchestrator_wxwidgets_routing.py::test_wxwidgets_handoff_excludes_electron_env",
    "tests/test_stop_on_success_orchestration.py::test_successful_first_gui_attempt_stops_remaining_strategy_iteration",
    "tests/test_stop_on_success_orchestration.py::test_successful_second_attempt_stops_third_attempt",
    "tests/test_stop_on_success_orchestration.py::test_failed_verification_still_allows_next_attempt",
    "tests/test_stop_on_success_orchestration.py::test_process_launch_without_verification_does_not_stop_retries",
    "tests/test_stop_on_success_orchestration.py::test_verified_codeblock_handoff_stops_later_attempts",
    "tests/test_verification_authority.py::TestOrchestratorVerificationAuthority::test_verification_persistence_failure_cannot_produce_succeeded",
    "tests/test_wine_gui_contract.py::test_native_console_pe_still_uses_exit_code_contract",
]


def load_order() -> list[str]:
    return [
        line.strip()
        for line in ORDER_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and "::" in line
    ]


def victim_fails(prefix: list[str], victim: str) -> bool:
    cmd = [sys.executable, "-m", "pytest", "-q", "--tb=no", *prefix, victim]
    env = {**dict(__import__("os").environ), "PYTHONPATH": str(ROOT)}
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    return result.returncode != 0


def find_polluter(order: list[str], victim: str) -> tuple[int, str | None]:
    idx = order.index(victim)
    lo, hi = 0, idx
    best = idx
    while lo < hi:
        mid = (lo + hi) // 2
        if victim_fails(order[:mid], victim):
            hi = mid
            best = mid
        else:
            lo = mid + 1
    polluter = order[best - 1] if best > 0 else None
    return best, polluter


def main() -> None:
    order = load_order()
    print(f"Collected {len(order)} tests\n")
    for victim in VICTIMS:
        best, polluter = find_polluter(order, victim)
        short = victim.split("::")[-1]
        print(f"VICTIM: {short}")
        print(f"  index={best} polluter={polluter}\n")


if __name__ == "__main__":
    main()
