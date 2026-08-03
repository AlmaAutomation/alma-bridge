"""Runtime conformance comparison models."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ConformanceClassification(str, Enum):
    EQUIVALENT = "equivalent"
    FUNCTIONALLY_EQUIVALENT = "functionally_equivalent"
    PARTIALLY_EQUIVALENT = "partially_equivalent"
    BEHAVIOR_CHANGED = "behavior_changed"
    CANDIDATE_FAILED = "candidate_failed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ConformanceScenario(BaseModel):
    scenario_id: str
    title: str
    baseline_provider_id: str
    candidate_provider_id: str
    file_path: str
    required_signals: List[str] = Field(default_factory=list)


class ConformanceRunResult(BaseModel):
    scenario_id: str
    baseline_provider_id: str
    candidate_provider_id: str
    classification: ConformanceClassification
    notes: List[str] = Field(default_factory=list)
    baseline_evidence: Dict[str, Any] = Field(default_factory=dict)
    candidate_evidence: Dict[str, Any] = Field(default_factory=dict)


class ConformanceReport(BaseModel):
    report_id: str
    results: List[ConformanceRunResult] = Field(default_factory=list)
    summary: Dict[str, int] = Field(default_factory=dict)
