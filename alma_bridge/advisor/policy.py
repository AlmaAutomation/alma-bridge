"""Deterministic phrase guards for advisor explanations."""

from __future__ import annotations

import re
from typing import Iterable, List, Sequence

from alma_bridge.advisor.models import AdvisorExplanation, AdvisorObservation, PolicyViolationError

FORBIDDEN_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\buse\s+\w",
        r"\bbest\s+strategy\b",
        r"\brequires?\s+vc\+\+",
        r"\binstall\s+vc\+\+",
        r"\bapplication\s+is\s+broken\b",
        r"\balma\s+recommends\b",
        r"\byou\s+should\b",
        r"\bswitch\s+to\b",
        r"\bfix\s+by\b",
        r"\bruntime_required\b",
        r"\bconfirmed_required\b",
    )
)

FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "requires vc++",
    "install vc++",
    "best strategy",
    "you should reinstall",
    "alma recommends",
    "application is broken",
    "switch to ",
    "fix by ",
)


def validate_statement(statement: str) -> List[str]:
    """Return policy violations for a single statement; empty when compliant."""
    text = (statement or "").strip()
    if not text:
        return ["empty statement"]
    violations: List[str] = []
    lowered = text.lower()
    for substring in FORBIDDEN_SUBSTRINGS:
        if substring in lowered:
            violations.append(f"forbidden phrase: {substring}")
    for pattern in FORBIDDEN_PATTERNS:
        if pattern.search(text):
            violations.append(f"forbidden pattern: {pattern.pattern}")
    return sorted(set(violations))


def validate_observation(observation: AdvisorObservation) -> None:
    violations = validate_statement(observation.statement)
    if not observation.evidence_references:
        violations.append("missing evidence references")
    if violations:
        raise PolicyViolationError(
            f"observation {observation.observation_id} violates advisor policy",
            violations=violations,
        )


def validate_explanation(explanation: AdvisorExplanation) -> None:
    violations: List[str] = []
    violations.extend(validate_statement(explanation.summary))
    for limitation in explanation.limitations:
        violations.extend(validate_statement(limitation))
    for observation in explanation.observations:
        try:
            validate_observation(observation)
        except PolicyViolationError as exc:
            violations.extend(exc.violations or [])
    if violations:
        raise PolicyViolationError(
            "advisor explanation violates language policy",
            violations=sorted(set(violations)),
        )


def explanation_contains_forbidden_language(text: str) -> bool:
    return bool(validate_statement(text))
