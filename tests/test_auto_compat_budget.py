"""AutoCompatibilityBudget tests."""

from __future__ import annotations

import time

import pytest

from alma_bridge.session.auto_compat_budget import (
    AUTO_COMPATIBILITY_BUDGET_EXHAUSTED,
    AutoCompatibilityBudget,
)


def test_repeated_identical_tuple_terminates():
    budget = AutoCompatibilityBudget(max_identical_tuple=3)
    for _ in range(2):
        assert budget.record_no_progress_tuple(
            program_identity="prog1",
            strategy_id="wine_host",
            remediation_ids=["a"],
            failure_signature="invalid_launch_args",
            state_fingerprint="fp1",
        ) is None
    reason = budget.record_no_progress_tuple(
        program_identity="prog1",
        strategy_id="wine_host",
        remediation_ids=["a"],
        failure_signature="invalid_launch_args",
        state_fingerprint="fp1",
    )
    assert reason is not None
    assert AUTO_COMPATIBILITY_BUDGET_EXHAUSTED in reason
    assert budget.exhaustion_dimension == "no_progress_tuple"


def test_improving_verification_confidence_resets_no_progress():
    budget = AutoCompatibilityBudget(max_identical_tuple=3)
    budget.record_no_progress_tuple(
        program_identity="prog1",
        strategy_id="wine_host",
        remediation_ids=["a"],
        failure_signature="invalid_launch_args",
        state_fingerprint="fp1",
        verification_confidence=0.1,
    )
    assert budget.record_no_progress_tuple(
        program_identity="prog1",
        strategy_id="wine_host",
        remediation_ids=["a"],
        failure_signature="invalid_launch_args",
        state_fingerprint="fp1",
        verification_confidence=0.5,
    ) is None
    assert not budget.exhausted


def test_execution_attempt_limit():
    budget = AutoCompatibilityBudget(max_execution_attempts=2)
    budget.record_execution_attempt()
    assert budget.check() is None
    budget.record_execution_attempt()
    assert budget.exhausted
    assert budget.exhaustion_dimension == "execution_attempts"


def test_wall_clock_budget(monkeypatch):
    budget = AutoCompatibilityBudget(wall_clock_sec=1, max_execution_attempts=1000)
    budget.started_monotonic = time.monotonic() - 2
    assert budget.check() is not None


def test_route_and_bridge_retry_limits():
    budget = AutoCompatibilityBudget(max_routes=1, max_bridge_retries=1, max_execution_attempts=100)
    budget.record_route()
    assert budget.exhausted
    budget2 = AutoCompatibilityBudget(max_routes=10, max_bridge_retries=1, max_execution_attempts=100)
    budget2.record_bridge_retry()
    assert budget2.exhausted


@pytest.mark.parametrize("signature", ["invalid_launch_args"])
def test_repeated_signature_tracked_but_not_alone_exhausting(signature):
    budget = AutoCompatibilityBudget(max_identical_tuple=10)
    for _ in range(5):
        budget.record_failure_signature(signature)
    assert not budget.exhausted
