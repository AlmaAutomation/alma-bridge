"""Decision plan review, approval, and export HTTP routes."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response

from alma_bridge.decision.errors import DecisionNotFoundError, MalformedDecisionEvidenceError
from alma_bridge.decision.models import DecisionInput
from alma_bridge.decision_review.errors import DecisionPlanMismatchError, DecisionReviewPolicyError
from alma_bridge.decision_review.models import (
    DecisionPlanArtifact,
    DecisionPlanDetail,
    DecisionPlanReview,
    DecisionPlanReviewRequest,
    ExportRequest,
)
from alma_bridge.decision_review.service import DecisionReviewService

router = APIRouter()
_service = DecisionReviewService()


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
    if isinstance(exc, DecisionReviewPolicyError):
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "violations": exc.violations},
        ) from exc
    raise exc


@router.get(
    "/bridge/decision/plans/{plan_id}",
    response_model=DecisionPlanDetail,
    tags=["Decision Review"],
)
def get_decision_plan(
    plan_id: str,
    session_id: Optional[str] = Query(default=None),
    application_fingerprint: Optional[str] = Query(default=None),
    baseline_session_id: Optional[str] = Query(default=None),
    comparison_session_id: Optional[str] = Query(default=None),
    ask_question: Optional[str] = Query(default=None),
) -> DecisionPlanDetail:
    try:
        return _service.get_plan_detail(
            plan_id,
            _decision_input_from_query(
                session_id=session_id,
                application_fingerprint=application_fingerprint,
                baseline_session_id=baseline_session_id,
                comparison_session_id=comparison_session_id,
                ask_question=ask_question,
            ),
        )
    except Exception as exc:
        _handle_errors(exc)
        raise AssertionError("unreachable")


@router.get(
    "/bridge/decision/plans/{plan_id}/reviews",
    response_model=List[DecisionPlanReview],
    tags=["Decision Review"],
)
def list_plan_reviews(
    plan_id: str,
    session_id: Optional[str] = Query(default=None),
    application_fingerprint: Optional[str] = Query(default=None),
) -> List[DecisionPlanReview]:
    try:
        if session_id or application_fingerprint:
            _service.get_plan_detail(
                plan_id,
                _decision_input_from_query(
                    session_id=session_id,
                    application_fingerprint=application_fingerprint,
                ),
            )
        return _service.list_reviews(plan_id)
    except Exception as exc:
        _handle_errors(exc)
        raise AssertionError("unreachable")


@router.get(
    "/bridge/decision/plans/{plan_id}/review/latest",
    response_model=DecisionPlanReview,
    tags=["Decision Review"],
)
def get_latest_plan_review(
    plan_id: str,
    session_id: Optional[str] = Query(default=None),
    application_fingerprint: Optional[str] = Query(default=None),
) -> DecisionPlanReview:
    try:
        if session_id or application_fingerprint:
            _service.get_plan_detail(
                plan_id,
                _decision_input_from_query(
                    session_id=session_id,
                    application_fingerprint=application_fingerprint,
                ),
            )
        review = _service.latest_review(plan_id)
        if review is None:
            raise HTTPException(status_code=404, detail=f"no reviews for plan {plan_id}")
        return review
    except HTTPException:
        raise
    except Exception as exc:
        _handle_errors(exc)
        raise AssertionError("unreachable")


@router.post(
    "/bridge/decision/plans/{plan_id}/reviews",
    response_model=DecisionPlanReview,
    tags=["Decision Review"],
)
def submit_plan_review(
    plan_id: str,
    payload: DecisionPlanReviewRequest,
    session_id: Optional[str] = Query(default=None),
    application_fingerprint: Optional[str] = Query(default=None),
    baseline_session_id: Optional[str] = Query(default=None),
    comparison_session_id: Optional[str] = Query(default=None),
    ask_question: Optional[str] = Query(default=None),
) -> DecisionPlanReview:
    try:
        return _service.submit_review(
            plan_id,
            _decision_input_from_query(
                session_id=session_id,
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


@router.post(
    "/bridge/decision/plans/{plan_id}/export",
    tags=["Decision Review"],
)
def export_plan(
    plan_id: str,
    payload: ExportRequest,
    session_id: Optional[str] = Query(default=None),
    application_fingerprint: Optional[str] = Query(default=None),
    baseline_session_id: Optional[str] = Query(default=None),
    comparison_session_id: Optional[str] = Query(default=None),
    ask_question: Optional[str] = Query(default=None),
) -> Response:
    try:
        artifact = _service.export_plan(
            plan_id,
            _decision_input_from_query(
                session_id=session_id,
                application_fingerprint=application_fingerprint,
                baseline_session_id=baseline_session_id,
                comparison_session_id=comparison_session_id,
                ask_question=ask_question,
            ),
            payload,
        )
        if payload.format == "markdown":
            return PlainTextResponse(
                content=artifact.content,
                media_type="text/markdown; charset=utf-8",
                headers={"X-Decision-Artifact-Id": artifact.artifact_id},
            )
        return Response(
            content=artifact.content,
            media_type="application/json",
            headers={"X-Decision-Artifact-Id": artifact.artifact_id},
        )
    except Exception as exc:
        _handle_errors(exc)
        raise AssertionError("unreachable")
