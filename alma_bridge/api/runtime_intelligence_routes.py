"""Read-only HTTP routes for Runtime Intelligence."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from alma_bridge.runtime_intelligence.models import (
    CorpusRequiredError,
    HypothesisNotFoundError,
    InvalidCorpusError,
    InvalidFamilyError,
)
from alma_bridge.runtime_intelligence.service import RuntimeIntelligenceService

router = APIRouter()


def _service() -> RuntimeIntelligenceService:
    return RuntimeIntelligenceService.shared()


def _parse_corpus(corpus: Optional[str]) -> str:
    if not corpus:
        raise HTTPException(status_code=400, detail="explicit corpus query parameter is required")
    try:
        _service().parse_corpus(corpus)
    except InvalidCorpusError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CorpusRequiredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return corpus


def _parse_family(family_id: str) -> str:
    try:
        _service().parse_family(family_id)
    except InvalidFamilyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return family_id


@router.get("/bridge/runtime-intelligence/families", tags=["Runtime Intelligence"])
def list_runtime_intelligence_families(corpus: Optional[str] = Query(None)):
    parsed = _parse_corpus(corpus)
    families = _service().get_families(RuntimeIntelligenceService.parse_corpus(parsed))
    return [summary.model_dump(mode="json") for summary in families]


@router.get("/bridge/runtime-intelligence/families/{family_id}", tags=["Runtime Intelligence"])
def get_runtime_intelligence_family(
    family_id: str,
    corpus: Optional[str] = Query(None),
):
    parsed_corpus = _parse_corpus(corpus)
    _parse_family(family_id)
    try:
        summary = _service().get_family(
            RuntimeIntelligenceService.parse_corpus(parsed_corpus),
            RuntimeIntelligenceService.parse_family(family_id),
        )
    except InvalidFamilyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return summary.model_dump(mode="json")


@router.get("/bridge/runtime-intelligence/index", tags=["Runtime Intelligence"])
def get_runtime_intelligence_index(
    corpus: Optional[str] = Query(None),
    family_id: Optional[str] = Query(None),
    provider_id: Optional[str] = Query(None),
):
    parsed_corpus = _parse_corpus(corpus)
    if not family_id:
        raise HTTPException(status_code=400, detail="family_id query parameter is required")
    if not provider_id:
        raise HTTPException(status_code=400, detail="provider_id query parameter is required")
    _parse_family(family_id)
    report = _service().get_index(
        RuntimeIntelligenceService.parse_corpus(parsed_corpus),
        RuntimeIntelligenceService.parse_family(family_id),
        provider_id,
    )
    return report.model_dump(mode="json")


@router.get("/bridge/runtime-intelligence/knowledge", tags=["Runtime Intelligence"])
def get_runtime_intelligence_knowledge(
    corpus: Optional[str] = Query(None),
    family_id: Optional[str] = Query(None),
    provider_id: Optional[str] = Query(None),
):
    parsed_corpus = _parse_corpus(corpus)
    if not family_id:
        raise HTTPException(status_code=400, detail="family_id query parameter is required")
    if not provider_id:
        raise HTTPException(status_code=400, detail="provider_id query parameter is required")
    _parse_family(family_id)
    report = _service().get_knowledge(
        RuntimeIntelligenceService.parse_corpus(parsed_corpus),
        RuntimeIntelligenceService.parse_family(family_id),
        provider_id,
    )
    return report.model_dump(mode="json")


@router.get("/bridge/runtime-intelligence/debt", tags=["Runtime Intelligence"])
def get_runtime_intelligence_debt(
    corpus: Optional[str] = Query(None),
    family_id: Optional[str] = Query(None),
    provider_id: Optional[str] = Query(None),
):
    parsed_corpus = _parse_corpus(corpus)
    if not family_id:
        raise HTTPException(status_code=400, detail="family_id query parameter is required")
    if not provider_id:
        raise HTTPException(status_code=400, detail="provider_id query parameter is required")
    _parse_family(family_id)
    report = _service().get_debt(
        RuntimeIntelligenceService.parse_corpus(parsed_corpus),
        RuntimeIntelligenceService.parse_family(family_id),
        provider_id,
    )
    return report.model_dump(mode="json")


@router.get("/bridge/runtime-intelligence/hypotheses", tags=["Runtime Intelligence"])
def list_runtime_intelligence_hypotheses(
    corpus: Optional[str] = Query(None),
    family_id: Optional[str] = Query(None),
):
    parsed_corpus = _parse_corpus(corpus)
    parsed_family = RuntimeIntelligenceService.parse_family(family_id) if family_id else None
    if family_id:
        _parse_family(family_id)
    snapshots = _service().list_hypotheses(
        RuntimeIntelligenceService.parse_corpus(parsed_corpus),
        family_id=parsed_family,
    )
    return [snapshot.model_dump(mode="json") for snapshot in snapshots]


@router.get("/bridge/runtime-intelligence/hypotheses/{hypothesis_id}", tags=["Runtime Intelligence"])
def get_runtime_intelligence_hypothesis(
    hypothesis_id: str,
    corpus: Optional[str] = Query(None),
):
    parsed_corpus = _parse_corpus(corpus)
    try:
        evaluation = _service().get_hypothesis(
            RuntimeIntelligenceService.parse_corpus(parsed_corpus),
            hypothesis_id,
        )
    except HypothesisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return evaluation.model_dump(mode="json")


@router.get("/bridge/runtime-intelligence/history", tags=["Runtime Intelligence"])
def get_runtime_intelligence_history(
    corpus: Optional[str] = Query(None),
    metric_id: Optional[str] = Query(None),
    family_id: Optional[str] = Query(None),
    provider_id: Optional[str] = Query(None),
):
    parsed_corpus = _parse_corpus(corpus)
    if not metric_id:
        raise HTTPException(status_code=400, detail="metric_id query parameter is required")
    parsed_family = RuntimeIntelligenceService.parse_family(family_id) if family_id else None
    if family_id:
        _parse_family(family_id)
    report = _service().get_history(
        RuntimeIntelligenceService.parse_corpus(parsed_corpus),
        metric_id,
        family_id=parsed_family,
        provider_id=provider_id,
    )
    return report.model_dump(mode="json")


@router.get("/bridge/runtime-intelligence/report", tags=["Runtime Intelligence"])
def get_runtime_intelligence_report(
    corpus: Optional[str] = Query(None),
    provider_id: Optional[str] = Query("native_alma"),
):
    parsed_corpus = _parse_corpus(corpus)
    report = _service().get_report(
        RuntimeIntelligenceService.parse_corpus(parsed_corpus),
        provider_id=provider_id or "native_alma",
    )
    return report.model_dump(mode="json")
