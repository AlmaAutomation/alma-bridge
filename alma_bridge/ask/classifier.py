"""Deterministic question classification for Ask Alma."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Tuple

from alma_bridge.ask.models import QuestionType


@dataclass(frozen=True)
class ClassificationResult:
    question_type: QuestionType


_RULES: Tuple[Tuple[QuestionType, Tuple[str, ...]], ...] = (
    (
        QuestionType.REMEDIATION_REFUSAL,
        (
            r"\bfix this\b",
            r"\bfix it\b",
            r"\bfix for me\b",
            r"\bshould i install\b",
            r"\binstall vc\+\+",
            r"\binstall dependency",
        ),
    ),
    (
        QuestionType.STRATEGY_RECOMMENDATION_REFUSAL,
        (
            r"\bwhich strategy should\b",
            r"\bbest strategy\b",
            r"\bwhat strategy should i use\b",
            r"\brecommend.*strategy\b",
        ),
    ),
    (
        QuestionType.REGRESSION_CHANGES,
        (
            r"\bwhat changed\b",
            r"\bwhy is this a regression\b",
            r"\bwhy is this session marked as a regression\b",
            r"\blatest session\b.*\bchange",
            r"\bchanged in the latest session\b",
        ),
    ),
    (
        QuestionType.EVIDENCE_PROVENANCE,
        (
            r"\bevidence supports\b",
            r"\bwhat evidence\b",
            r"\bshow evidence\b",
            r"\bprovenance\b",
            r"\bwhy.*detected\b",
        ),
    ),
    (
        QuestionType.CONFLICTING_EVIDENCE,
        (
            r"\bconflict",
            r"\bconflicting evidence\b",
            r"\bcompeting framework",
        ),
    ),
    (
        QuestionType.RUNTIME_OBSERVATIONS,
        (
            r"\bruntime",
            r"\bvc\+\+",
            r"\bobserved runtime",
        ),
    ),
    (
        QuestionType.FRAMEWORK_HISTORY,
        (
            r"\bframework",
            r"\bwxwidgets\b",
            r"\bqt\b",
            r"\bwhich frameworks\b",
        ),
    ),
    (
        QuestionType.LAUNCH_STRATEGY_HISTORY,
        (
            r"\bwine_gui\b",
            r"\blaunch strategy\b",
            r"\bstrategy.*success",
            r"\bstrategies have succeeded\b",
        ),
    ),
    (
        QuestionType.VERIFICATION_HISTORY,
        (
            r"\bworked before\b",
            r"\bhas .* worked\b",
            r"\bverified success",
            r"\bsucceeded before\b",
            r"\bauthoritatively verified\b",
        ),
    ),
    (
        QuestionType.COMPATIBILITY_SUMMARY,
        (
            r"\bcompatibility summary\b",
            r"\bwhat does alma know\b",
            r"\bsummary\b",
            r"\bhas this application worked\b",
        ),
    ),
)


class QuestionClassifier:
    """Deterministic pattern-based question classifier."""

    def classify(self, question: str) -> ClassificationResult:
        normalized = " ".join((question or "").lower().split())
        for question_type, patterns in _RULES:
            if any(re.search(pattern, normalized) for pattern in patterns):
                return ClassificationResult(question_type=question_type)
        return ClassificationResult(question_type=QuestionType.UNSUPPORTED)
