from __future__ import annotations

"""Typed distinction between shadow trust categories and operator validation labels."""

from enum import Enum
from typing import FrozenSet, Optional, Union


class TrustCategory(str, Enum):
    REJECTED = "rejected"
    SHADOW_OBSERVATION_ONLY = "shadow_observation_only"
    ELIGIBLE_FOR_FUTURE_ACTIVE_REUSE = "eligible_for_future_active_reuse"


class ValidationLabelType(str, Enum):
    ELIGIBLE_CORRECT = "eligible_correct"
    ELIGIBLE_INCORRECT = "eligible_incorrect"
    REJECTED_CORRECT = "rejected_correct"
    REJECTED_INCORRECT = "rejected_incorrect"
    DRIFT_CORRECT = "drift_correct"
    DRIFT_INCORRECT = "drift_incorrect"
    WINNER_CORRECT = "winner_correct"
    WINNER_INCORRECT = "winner_incorrect"
    INDETERMINATE = "indeterminate"


VALID_LABEL_TYPES: FrozenSet[str] = frozenset(item.value for item in ValidationLabelType)
TRUST_CATEGORIES: FrozenSet[str] = frozenset(item.value for item in TrustCategory)

# Trust categories must never be submitted as operator labels.
TRUST_CATEGORY_AS_LABEL_BLOCKLIST: FrozenSet[str] = TRUST_CATEGORIES


def parse_validation_label_type(value: str) -> ValidationLabelType:
    normalized = str(value or "").strip()
    if normalized in TRUST_CATEGORY_AS_LABEL_BLOCKLIST:
        raise ValueError(
            f"invalid label_type: {normalized!r} is a trust category, not a validation label"
        )
    try:
        return ValidationLabelType(normalized)
    except ValueError as exc:
        raise ValueError(f"invalid label_type: {normalized}") from exc


def parse_trust_category(value: str) -> TrustCategory:
    try:
        return TrustCategory(str(value or "").strip())
    except ValueError as exc:
        raise ValueError(f"invalid trust_category: {value!r}") from exc


def is_trust_category_value(value: str) -> bool:
    return str(value or "").strip() in TRUST_CATEGORIES


def expected_imported_trust_label() -> ValidationLabelType:
    """Imported trust: shadow observes only; operator labels rejection correctness."""
    return ValidationLabelType.REJECTED_CORRECT


def validate_label_not_trust_category(label_type: Union[str, ValidationLabelType]) -> str:
    if isinstance(label_type, ValidationLabelType):
        return label_type.value
    return parse_validation_label_type(str(label_type)).value
