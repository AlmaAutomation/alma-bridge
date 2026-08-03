"""Approved plan validation and dry-run HTTP routes."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from alma_bridge.decision.errors import DecisionNotFoundError, MalformedDecisionEvidenceError
from alma_bridge.decision.models import DecisionInput
from alma_bridge.decision_review.errors import DecisionPlanMismatchError
from alma_bridge.decision_validation.errors import (
    DecisionValidationModeError,
    DecisionValidationNotFoundError,
)
from alma_bridge.decision_validation.models import DecisionPlanDryRunReport, ValidationRequest
from alma_bridge.decision_validation.service import DecisionValidationService

router = APIRouter()
_service = DecisionValidationService()


def _decision_input_from_query(
    *,
    session_id: Optional[str] = None,
    application_fingerprint: Optional[str] = None,
    baseline_session_id: Optional[str] = None,
    comparison_session_id: Optional[str] = None,
    ask_question: Optional[str] = None,
) -> DecisionInput:
    if not session_id and not application_fingerprint:
        raise HTTPException(
            status_code=400,
            detail="session_id or application_fingerprint query parameter is required",
        )
    return DecisionInput(
        session_id=session_id,
        application_fingerprint=application_fingerprint,
        baseline_session_id=baseline_session_id,
        comparison_session_id=comparison_session_id,
        ask_question=ask_question,
    )


def _handle_errors(exc: Exception) -> None:
    if isinstance(exc, DecisionNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, MalformedDecisionEvidenceError):
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.details},
        ) from exc
    if isinstance(exc, DecisionPlanMismatchError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, DecisionValidationNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, DecisionValidationModeError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


@router.post(
    "/bridge/decision/plans/{plan_id}/validate",
    response_model=DecisionPlanDryRunReport,
    tags=["Decision Validation"],
)
def validate_plan(
    plan_id: str,
    payload: ValidationRequest,
    session_id: Optional[str] = Query(default=None),
    application_fingerprint: Optional[str] = Query(default=None),
    baseline_session_id: Optional[str] = Query(default=None),
    comparison_session_id: Optional[str] = Query(default=None),
    ask_question: Optional[str] = Query(default=None),
) -> DecisionPlanDryRunReport:
    try:
        return _service.validate_plan(
            plan_id,
            _decision_input_from_query(
                session_id=session_id or payload.session_id,
                application_fingerprint=application_fingerprint,
                baseline_session_id=baseline_session_id,
                comparison_session_id=comparison_session_id,
                ask_question=ask_question,
            ),
            payload,
        )
    except Exception as exc:
        _handle_errors(exc)
        raise AssertionError("unreachable")


@router.get(
    "/bridge/decision/plans/{plan_id}/validations",
    response_model=List[DecisionPlanDryRunReport],
    tags=["Decision Validation"],
)
def list_plan_validations(
    plan_id: str,
    session_id: Optional[str] = Query(default=None),
    application_fingerprint: Optional[str] = Query(default=None),
) -> List[DecisionPlanDryRunReport]:
    try:
        if session_id or application_fingerprint:
            _service._review.get_plan_detail(  # noqa: SLF001
                plan_id,
                _decision_input_from_query(
                    session_id=session_id,
                    application_fingerprint=application_fingerprint,
                ),
            )
        return _service.list_validations(plan_id)
    except Exception as exc:
        _handle_errors(exc)
        raise AssertionError("unreachable")


@router.get(
    "/bridge/decision/plans/{plan_id}/validation/latest",
    response_model=DecisionPlanDryRunReport,
    tags=["Decision Validation"],
)
def get_latest_plan_validation(
    plan_id: str,
    session_id: Optional[str] = Query(default=None),
    application_fingerprint: Optional[str] = Query(default=None),
) -> DecisionPlanDryRunReport:
    try:
        if session_id or application_fingerprint:
            _service._review.get_plan_detail(  # noqa: SLF001
                plan_id,
                _decision_input_from_query(
                    session_id=session_id,
                    application_fingerprint=application_fingerprint,
                ),
            )
        report = _service.latest_validation(plan_id)
        if report is None:
            raise HTTPException(status_code=404, detail=f"no validations for plan {plan_id}")
        return report
    except HTTPException:
        raise
    except Exception as exc:
        _handle_errors(exc)
        raise AssertionError("unreachable")
