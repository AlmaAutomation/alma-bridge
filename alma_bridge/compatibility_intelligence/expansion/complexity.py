"""Engineering complexity assessment with factor explanations."""

from __future__ import annotations

from typing import List, Optional, Tuple

from alma_bridge.compatibility_intelligence.capabilities import get_capability
from alma_bridge.compatibility_intelligence.expansion.models import (
    ComplexityAssessment,
    EngineeringComplexityLevel,
)
from alma_bridge.compatibility_intelligence.models import ApiComplexity

_BEHAVIOR_COMPLEXITY: dict[str, Tuple[EngineeringComplexityLevel, List[str]]] = {
    "append_existing_file": (
        EngineeringComplexityLevel.MEDIUM,
        [
            "Requires OPEN_EXISTING + FILE_APPEND_DATA flag semantics",
            "File pointer positioning at end-of-file",
            "Host filesystem append mapping",
            "Error modes for sharing violations",
        ],
    ),
    "overlapped_io": (
        EngineeringComplexityLevel.HIGH,
        [
            "Async I/O completion callbacks",
            "Overlapped structure lifetime",
            "Event/synchronization primitives",
        ],
    ),
    "open_existing_readwrite": (
        EngineeringComplexityLevel.LOW,
        [
            "OPEN_EXISTING disposition handling",
            "Read/write access mode mapping",
        ],
    ),
    "set_environment_variable": (
        EngineeringComplexityLevel.MEDIUM,
        [
            "Process environment block mutation",
            "Memory ownership of environment strings",
        ],
    ),
    "write_stdout": (
        EngineeringComplexityLevel.TRIVIAL,
        [
            "Single API (WriteFile on stdout handle)",
            "No callbacks or async",
        ],
    ),
    "process_exit_with_code": (
        EngineeringComplexityLevel.TRIVIAL,
        [
            "Single API (ExitProcess)",
            "No host abstraction breadth",
        ],
    ),
    "create_always_write": (
        EngineeringComplexityLevel.LOW,
        [
            "CREATE_ALWAYS disposition",
            "Sequential WriteFile",
        ],
    ),
    "sequential_read": (
        EngineeringComplexityLevel.LOW,
        [
            "ReadFile sequential I/O",
            "Handle close semantics",
        ],
    ),
}

_CAPABILITY_BASE: dict[str, Tuple[EngineeringComplexityLevel, List[str]]] = {
    "filesystem.basic_io": (
        EngineeringComplexityLevel.MEDIUM,
        ["Win32 file API surface", "Handle lifecycle", "Path normalization"],
    ),
    "console.stdout": (
        EngineeringComplexityLevel.TRIVIAL,
        ["Std handle retrieval", "WriteFile to console"],
    ),
    "process.environment": (
        EngineeringComplexityLevel.LOW,
        ["Environment block read path"],
    ),
    "process.creation": (
        EngineeringComplexityLevel.VERY_HIGH,
        [
            "Process creation APIs",
            "Command line and environment inheritance",
            "Handle inheritance table",
            "Security descriptor propagation",
        ],
    ),
    "threading.basic": (
        EngineeringComplexityLevel.HIGH,
        [
            "Thread creation and synchronization",
            "TEB/PEB interaction",
            "Critical section semantics",
        ],
    ),
    "gui.windowing": (
        EngineeringComplexityLevel.VERY_HIGH,
        [
            "user32/gdi32 surface",
            "Message loop and window class registration",
            "Cross-process HWND state",
        ],
    ),
    "dotnet.clr": (
        EngineeringComplexityLevel.VERY_HIGH,
        [
            "CLR hosting and metadata",
            "Managed/unmanaged boundary",
        ],
    ),
    "api.unknown": (
        EngineeringComplexityLevel.UNKNOWN,
        ["Unclassified API — complexity cannot be determined"],
    ),
}


def _api_complexity_to_level(complexity: ApiComplexity) -> EngineeringComplexityLevel:
    if complexity == ApiComplexity.LOW:
        return EngineeringComplexityLevel.LOW
    if complexity == ApiComplexity.MEDIUM:
        return EngineeringComplexityLevel.MEDIUM
    return EngineeringComplexityLevel.HIGH


def _level_to_score(level: EngineeringComplexityLevel) -> float:
    mapping = {
        EngineeringComplexityLevel.TRIVIAL: 0.05,
        EngineeringComplexityLevel.LOW: 0.2,
        EngineeringComplexityLevel.MEDIUM: 0.45,
        EngineeringComplexityLevel.HIGH: 0.7,
        EngineeringComplexityLevel.VERY_HIGH: 0.95,
        EngineeringComplexityLevel.UNKNOWN: 0.5,
    }
    return mapping[level]


def assess_complexity(
    capability_id: str,
    behavior_id: Optional[str] = None,
    *,
    api_count: int = 1,
) -> ComplexityAssessment:
    """Deterministic complexity from capability, behavior, and API count."""
    factors: List[str] = []

    if behavior_id and behavior_id in _BEHAVIOR_COMPLEXITY:
        level, behavior_factors = _BEHAVIOR_COMPLEXITY[behavior_id]
        factors.extend(behavior_factors)
    elif capability_id in _CAPABILITY_BASE:
        level, cap_factors = _CAPABILITY_BASE[capability_id]
        factors.extend(cap_factors)
    else:
        cap = get_capability(capability_id)
        if cap:
            level = _api_complexity_to_level(cap.complexity)
            factors.append(f"Registry complexity: {cap.complexity.value}")
        else:
            level = EngineeringComplexityLevel.UNKNOWN
            factors.append("Capability not in registry")

    if api_count > 3:
        factors.append(f"Multiple APIs involved ({api_count})")
        if level == EngineeringComplexityLevel.LOW:
            level = EngineeringComplexityLevel.MEDIUM
        elif level == EngineeringComplexityLevel.MEDIUM:
            level = EngineeringComplexityLevel.HIGH

    if api_count == 1 and level not in (
        EngineeringComplexityLevel.VERY_HIGH,
        EngineeringComplexityLevel.UNKNOWN,
    ):
        factors.append("Single primary API symbol")

    score = _level_to_score(level)
    return ComplexityAssessment(level=level, score=score, factors=factors)


def engineering_cost_score(complexity: ComplexityAssessment) -> float:
    """Invert complexity to cost score — higher is cheaper/easier."""
    return round(1.0 - complexity.score, 4)
