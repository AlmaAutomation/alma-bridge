"""Read-only session comparison HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from alma_bridge.comparison.models import (
    ComparisonFingerprintMismatchError,
    ComparisonNotFoundError,
    MalformedComparisonEvidenceError,
    SessionEnvironmentComparison,
)
from alma_bridge.comparison.service import SessionComparisonService

router = APIRouter()
_service = SessionComparisonService()


@router.get(
    "/bridge/comparison/sessions/{baseline_session_id}/{comparison_session_id}",
    response_model=SessionEnvironmentComparison,
    tags=["Comparison"],
)
def compare_sessions(
    baseline_session_id: str,
    comparison_session_id: str,
) -> SessionEnvironmentComparison:
    try:
        return _service.compare_sessions(baseline_session_id, comparison_session_id)
    except ComparisonNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ComparisonFingerprintMismatchError as exc:
        raise HTTPException(status_code=422, detail={"message": str(exc), "errors": []}) from exc
    except MalformedComparisonEvidenceError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.details},
        ) from exc


@router.get(
    "/bridge/comparison/applications/{fingerprint}",
    response_model=SessionEnvironmentComparison,
    tags=["Comparison"],
)
def compare_application_sessions(
    fingerprint: str,
    baseline: str = Query(..., alias="baseline"),
    comparison: str = Query(..., alias="comparison"),
) -> SessionEnvironmentComparison:
    try:
        return _service.compare_for_application(
            fingerprint,
            baseline_session_id=baseline,
            comparison_session_id=comparison,
        )
    except ComparisonNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ComparisonFingerprintMismatchError as exc:
        raise HTTPException(status_code=422, detail={"message": str(exc), "errors": []}) from exc
    except MalformedComparisonEvidenceError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.details},
        ) from exc
