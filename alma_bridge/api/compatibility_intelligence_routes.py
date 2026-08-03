"""HTTP routes for Alma Compatibility Intelligence."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from alma_bridge.compatibility_intelligence.apis import list_registry_entries
from alma_bridge.compatibility_intelligence.capabilities import list_capabilities
from alma_bridge.compatibility_intelligence.models import (
    CompatibilityAnalysisResult,
    RegistryMetrics,
)
from alma_bridge.compatibility_intelligence.service import CompatibilityIntelligenceService

router = APIRouter()
_service = CompatibilityIntelligenceService()


class AnalyzeRequest(BaseModel):
    file_path: str
    persist: bool = True


@router.post(
    "/bridge/compatibility/analyze",
    response_model=CompatibilityAnalysisResult,
    tags=["Compatibility Intelligence"],
)
def analyze_executable(request: AnalyzeRequest) -> CompatibilityAnalysisResult:
    """Analyze a PE binary for required capabilities and provider coverage (read-only)."""
    try:
        return _service.analyze(request.file_path, persist=request.persist)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/bridge/compatibility/history",
    response_model=List[CompatibilityAnalysisResult],
    tags=["Compatibility Intelligence"],
)
def analysis_history(limit: int = 50) -> List[CompatibilityAnalysisResult]:
    return _service.list_history(limit=limit)


@router.get(
    "/bridge/compatibility/analysis/{digest}",
    response_model=CompatibilityAnalysisResult,
    tags=["Compatibility Intelligence"],
)
def get_analysis(digest: str) -> CompatibilityAnalysisResult:
    result = _service.get_by_digest(digest)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No analysis for digest: {digest}")
    return result


@router.get(
    "/bridge/compatibility/capabilities",
    tags=["Compatibility Intelligence"],
)
def capability_registry():
    caps = list_capabilities()
    return [
        {
            "capability_id": c.capability_id,
            "description": c.description,
            "complexity": c.complexity.value,
            "native": c.native.value,
            "wine": c.wine.value,
            "proton": c.proton.value,
            "stability": c.stability,
            "documentation_ref": c.documentation_ref,
        }
        for c in caps
    ]


@router.get(
    "/bridge/compatibility/apis",
    tags=["Compatibility Intelligence"],
)
def api_registry():
    return [
        {
            "dll": e.dll,
            "function": e.function,
            "capability_id": e.capability_id,
            "complexity": e.complexity.value,
            "native_status": e.native_status.value,
            "wine_status": e.wine_status.value,
            "documentation_ref": e.documentation_ref,
        }
        for e in list_registry_entries()
    ]


@router.get(
    "/bridge/compatibility/metrics",
    response_model=RegistryMetrics,
    tags=["Compatibility Intelligence"],
)
def registry_metrics() -> RegistryMetrics:
    return _service.get_registry_metrics()


@router.get(
    "/bridge/compatibility/predict",
    tags=["Compatibility Intelligence"],
)
def predict_from_path(file_path: str) -> dict:
    """Quick prediction endpoint — returns prediction subset only."""
    try:
        result = _service.analyze(file_path, persist=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "analysis_id": result.analysis_id,
        "binary_digest": result.binary_digest,
        "prediction": result.prediction.model_dump(),
        "coverage": {
            pid: breakdown.model_dump()
            for pid, breakdown in result.coverage.providers.items()
        },
    }
