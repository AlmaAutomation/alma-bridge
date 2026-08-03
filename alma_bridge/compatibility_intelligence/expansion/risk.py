"""Security and semantic risk categories — dimensions preserved separately."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from alma_bridge.compatibility_intelligence.expansion.models import (
    SecurityRiskAssessment,
    SecurityRiskCategory,
    SemanticRiskAssessment,
    SemanticRiskCategory,
)

_CAPABILITY_SECURITY: dict[str, List[Tuple[SecurityRiskCategory, str]]] = {
    "filesystem.basic_io": [
        (
            SecurityRiskCategory.FILESYSTEM_ESCAPE,
            "File path normalization may escape intended sandbox directory",
        ),
        (
            SecurityRiskCategory.PARSER_ATTACK_SURFACE,
            "Path parsing and wide-character conversion",
        ),
    ],
    "process.creation": [
        (
            SecurityRiskCategory.ARBITRARY_PROCESS_CREATION,
            "Unbounded child process creation surface",
        ),
        (
            SecurityRiskCategory.PRIVILEGE_BOUNDARY,
            "Inherited handles and security context",
        ),
    ],
    "threading.basic": [
        (
            SecurityRiskCategory.SYNCHRONIZATION_DEADLOCK,
            "Lock ordering and deadlock potential",
        ),
        (
            SecurityRiskCategory.PRIVILEGE_BOUNDARY,
            "Cross-thread shared mutable state",
        ),
    ],
    "registry.read": [
        (
            SecurityRiskCategory.REGISTRY_PERSISTENCE,
            "Registry read may expose host configuration",
        ),
    ],
    "registry.write": [
        (
            SecurityRiskCategory.REGISTRY_PERSISTENCE,
            "Registry write enables host persistence",
        ),
    ],
    "gui.windowing": [
        (
            SecurityRiskCategory.PRIVILEGE_BOUNDARY,
            "Window message injection surface",
        ),
    ],
}

_BEHAVIOR_SECURITY: dict[str, List[Tuple[SecurityRiskCategory, str]]] = {
    "append_existing_file": [
        (
            SecurityRiskCategory.FILESYSTEM_ESCAPE,
            "Append mode must not bypass path confinement",
        ),
    ],
    "overlapped_io": [
        (
            SecurityRiskCategory.SYNCHRONIZATION_DEADLOCK,
            "Async completion may introduce races",
        ),
    ],
}

_CAPABILITY_SEMANTIC: dict[str, List[Tuple[SemanticRiskCategory, str]]] = {
    "filesystem.basic_io": [
        (
            SemanticRiskCategory.UNMODELED_FLAGS_OR_MODES,
            "CreateFile access flags and share modes vary widely",
        ),
        (
            SemanticRiskCategory.BROAD_BEHAVIOR_SURFACE,
            "File I/O semantics span many flag combinations",
        ),
    ],
    "process.creation": [
        (
            SemanticRiskCategory.BROAD_BEHAVIOR_SURFACE,
            "Process creation flags and inheritance modes",
        ),
        (
            SemanticRiskCategory.CROSS_PROCESS_STATE,
            "Parent/child handle and environment sharing",
        ),
    ],
    "threading.basic": [
        (
            SemanticRiskCategory.ASYNC_CALLBACKS,
            "Thread proc callbacks and TLS initialization",
        ),
    ],
    "gui.windowing": [
        (
            SemanticRiskCategory.BROAD_BEHAVIOR_SURFACE,
            "Window class, message pump, and GDI semantics",
        ),
    ],
    "api.unknown": [
        (
            SemanticRiskCategory.UNDOCUMENTED_BEHAVIOR,
            "API semantics unknown — cannot assess behavior surface",
        ),
    ],
}

_BEHAVIOR_SEMANTIC: dict[str, List[Tuple[SemanticRiskCategory, str]]] = {
    "append_existing_file": [
        (
            SemanticRiskCategory.UNMODELED_FLAGS_OR_MODES,
            "FILE_APPEND_DATA vs generic write semantics",
        ),
        (
            SemanticRiskCategory.VERSION_SPECIFIC_BEHAVIOR,
            "Append pointer behavior may differ by Windows version",
        ),
    ],
    "overlapped_io": [
        (
            SemanticRiskCategory.ASYNC_CALLBACKS,
            "Completion routine invocation semantics",
        ),
    ],
}


def _merge_risk_entries(
    entries: List[Tuple],
) -> Tuple[List, Dict[str, str]]:
    categories: List = []
    explanations: Dict[str, str] = {}
    seen: set = set()
    for cat, explanation in entries:
        if cat.value not in seen:
            categories.append(cat)
            seen.add(cat.value)
        explanations[cat.value] = explanation
    return categories, explanations


def _score_from_category_count(count: int, max_ref: int = 5) -> float:
    return round(min(1.0, count / max_ref), 4)


def assess_security_risk(
    capability_id: str,
    behavior_id: Optional[str] = None,
) -> SecurityRiskAssessment:
    entries: List[Tuple[SecurityRiskCategory, str]] = []
    entries.extend(_CAPABILITY_SECURITY.get(capability_id, []))
    if behavior_id:
        entries.extend(_BEHAVIOR_SECURITY.get(behavior_id, []))
    if not entries and capability_id.startswith("process."):
        entries.append(
            (
                SecurityRiskCategory.PRIVILEGE_BOUNDARY,
                "Process-related capability requires privilege review",
            )
        )
    categories, explanations = _merge_risk_entries(entries)
    score = _score_from_category_count(len(categories))
    return SecurityRiskAssessment(
        categories=categories, score=score, explanations=explanations
    )


def assess_semantic_risk(
    capability_id: str,
    behavior_id: Optional[str] = None,
) -> SemanticRiskAssessment:
    entries: List[Tuple[SemanticRiskCategory, str]] = []
    entries.extend(_CAPABILITY_SEMANTIC.get(capability_id, []))
    if behavior_id:
        entries.extend(_BEHAVIOR_SEMANTIC.get(behavior_id, []))
    categories, explanations = _merge_risk_entries(entries)
    score = _score_from_category_count(len(categories))
    return SemanticRiskAssessment(
        categories=categories, score=score, explanations=explanations
    )


def invert_risk_score(risk_score: float) -> float:
    """Higher return = lower risk (for composite weighting visibility)."""
    return round(1.0 - risk_score, 4)
