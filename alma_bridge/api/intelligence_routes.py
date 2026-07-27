"""Read-only Compatibility Intelligence HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from alma_bridge.intelligence.models import CompatibilityAssessment, IntelligenceNotFoundError, MalformedEvidenceError
from alma_bridge.intelligence.service import CompatibilityIntelligenceService

router = APIRouter()
_service = CompatibilityIntelligenceService()


@router.get(
    "/bridge/intelligence/sessions/{session_id}",
    response_model=CompatibilityAssessment,
    tags=["Intelligence"],
)
def intelligence_for_session(session_id: str) -> CompatibilityAssessment:
    try:
        return _service.assess_session(session_id)
    except IntelligenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MalformedEvidenceError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.details},
        ) from exc


@router.get(
    "/bridge/intelligence/applications/{fingerprint}",
    response_model=CompatibilityAssessment,
    tags=["Intelligence"],
)
def intelligence_for_application(fingerprint: str) -> CompatibilityAssessment:
    try:
        return _service.assess_application(fingerprint)
    except IntelligenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MalformedEvidenceError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.details},
        ) from exc
