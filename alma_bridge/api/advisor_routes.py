"""Read-only Compatibility Advisor HTTP routes."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query

from alma_bridge.advisor.models import (
    AdvisorExplanationResponse,
    AdvisorNotFoundError,
    MalformedAdvisorError,
    PolicyViolationError,
)
from alma_bridge.advisor.service import CompatibilityAdvisorService

router = APIRouter()
_service = CompatibilityAdvisorService()


@router.get(
    "/bridge/advisor/applications/{fingerprint}",
    response_model=AdvisorExplanationResponse,
    tags=["Advisor"],
)
def advisor_for_application(
    fingerprint: str,
    session_id: Optional[str] = Query(default=None),
    render: Literal["deterministic", "llm"] = Query(default="deterministic"),
) -> AdvisorExplanationResponse:
    try:
        return _service.explain_for_application(
            fingerprint,
            session_id=session_id,
            render=render,
        )
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
    response_model=AdvisorExplanationResponse,
    tags=["Advisor"],
)
def advisor_for_session(
    session_id: str,
    render: Literal["deterministic", "llm"] = Query(default="deterministic"),
) -> AdvisorExplanationResponse:
    try:
        return _service.explain_for_session(session_id, render=render)
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
