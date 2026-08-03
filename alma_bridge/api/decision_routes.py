"""Read-only Decision Engine HTTP routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from alma_bridge.decision.errors import DecisionNotFoundError, MalformedDecisionEvidenceError
from alma_bridge.decision.models import DecisionInput, DecisionPlan
from alma_bridge.decision.service import DecisionService

router = APIRouter()
_service = DecisionService()


@router.get(
    "/bridge/decision/plan",
    response_model=DecisionPlan,
    tags=["Decision"],
)
def decision_plan_get(
    session_id: Optional[str] = Query(default=None),
    application_fingerprint: Optional[str] = Query(default=None),
    baseline_session_id: Optional[str] = Query(default=None),
    comparison_session_id: Optional[str] = Query(default=None),
    ask_question: Optional[str] = Query(default=None),
) -> DecisionPlan:
    if not session_id and not application_fingerprint:
        raise HTTPException(
            status_code=400,
            detail="session_id or application_fingerprint query parameter is required",
        )
    try:
        return _service.plan_from_input(
            DecisionInput(
                session_id=session_id,
                application_fingerprint=application_fingerprint,
                baseline_session_id=baseline_session_id,
                comparison_session_id=comparison_session_id,
                ask_question=ask_question,
            )
        )
    except DecisionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MalformedDecisionEvidenceError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.details},
        ) from exc


@router.post(
    "/bridge/decision/plan",
    response_model=DecisionPlan,
    tags=["Decision"],
)
def decision_plan_post(payload: DecisionInput) -> DecisionPlan:
    try:
        return _service.plan_from_input(payload)
    except DecisionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MalformedDecisionEvidenceError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.details},
        ) from exc
