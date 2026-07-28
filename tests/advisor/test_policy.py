"""Policy guard tests for advisor language."""

from __future__ import annotations

import pytest

from alma_bridge.advisor.policy import (
    explanation_contains_forbidden_language,
    validate_statement,
)


@pytest.mark.parametrize(
    "statement",
    [
        "Use wine_gui.",
        "Best strategy is wine_gui.",
        "Requires VC++.",
        "Install VC++.",
        "Application is broken.",
        "Alma recommends switching prefix.",
        "You should reinstall dependencies.",
        "Switch to proton.",
        "Fix by installing winetricks.",
    ],
)
def test_forbidden_recommendation_language(statement):
    assert explanation_contains_forbidden_language(statement)


@pytest.mark.parametrize(
    "statement",
    [
        "Three prior sessions were authoritatively verified successful using wine_gui.",
        "wxWidgets was observed in 4 sessions.",
        "VC++ runtime was observed in 5 verified sessions.",
        "A verified failure was observed in the latest session.",
    ],
)
def test_allowed_factual_language(statement):
    assert validate_statement(statement) == []


def test_empty_statement_is_forbidden():
    assert validate_statement("") == ["empty statement"]
