"""Policy gate ActionIntent tests."""

from __future__ import annotations

import pytest

from alma_bridge.session.policy import (
    ActionIntent,
    ActionType,
    ExecutionScope,
    MutationScope,
    PolicyGate,
)


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.bridge_auto_remediate", True)
    monkeypatch.setattr("alma_bridge.config.settings.operator_allow_mutations", False)


def _intent(**overrides):
    base = dict(
        action_id="remediation:dotnet",
        action_type=ActionType.REMEDIATION,
        mutation_scope=MutationScope.WINE_PREFIX,
        execution_scope=ExecutionScope.BRIDGE_SESSION,
        risk="medium",
        actor="test",
        session_id="sess-1",
        correlation_id="sess-1",
        prefix_key="/tmp/prefix",
    )
    base.update(overrides)
    return ActionIntent(**base)


def test_wine_prefix_allowed_when_auto_remediate_on():
    decision = PolicyGate().evaluate(_intent())
    assert decision.allowed is True


def test_wine_prefix_blocked_when_auto_remediate_off(monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.bridge_auto_remediate", False)
    decision = PolicyGate().evaluate(_intent(auto_remediate_requested=False))
    assert decision.allowed is False
    assert decision.approval_required is True


def test_host_mutation_blocked_without_operator_mutations():
    decision = PolicyGate().evaluate(
        _intent(
            action_id="pathway:apt",
            action_type=ActionType.ROUTE,
            mutation_scope=MutationScope.HOST_PACKAGES,
        )
    )
    assert decision.allowed is False
