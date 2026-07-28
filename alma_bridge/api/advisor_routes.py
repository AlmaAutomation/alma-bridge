"""Read-only Compatibility Advisor HTTP routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from alma_bridge.advisor.models import (
    AdvisorExplanation,
    AdvisorNotFoundError,
    MalformedAdvisorError,
    PolicyViolationError,
)
from alma_bridge.advisor.service import CompatibilityAdvisorService

router = APIRouter()
_service = CompatibilityAdvisorService()


@router.get(
    "/bridge/advisor/applications/{fingerprint}",
    response_model=AdvisorExplanation,
    tags=["Advisor"],
)
def advisor_for_application(
    fingerprint: str,
    session_id: Optional[str] = Query(default=None),
) -> AdvisorExplanation:
    try:
        return _service.explain_for_application(fingerprint, session_id=session_id)
    except AdvisorNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MalformedAdvisorError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.details},
        ) from exc
    except PolicyViolationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.violations},
        ) from exc


@router.get(
    "/bridge/advisor/sessions/{session_id}",
    response_model=AdvisorExplanation,
    tags=["Advisor"],
)
def advisor_for_session(session_id: str) -> AdvisorExplanation:
    try:
        return _service.explain_for_session(session_id)
    except AdvisorNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MalformedAdvisorError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.details},
        ) from exc
    except PolicyViolationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.violations},
        ) from exc
