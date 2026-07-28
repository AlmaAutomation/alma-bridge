"""Read-only Compatibility Regression HTTP routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from alma_bridge.knowledge.models import MalformedKnowledgeEvidenceError
from alma_bridge.regression.models import (
    CompatibilityRegressionReport,
    RegressionNotFoundError,
)
from alma_bridge.regression.service import CompatibilityRegressionService

router = APIRouter()
_service = CompatibilityRegressionService()


@router.get(
    "/bridge/regression/applications/{fingerprint}",
    response_model=CompatibilityRegressionReport,
    tags=["Regression"],
)
def regression_for_application(
    fingerprint: str,
    session_id: Optional[str] = Query(default=None),
) -> CompatibilityRegressionReport:
    try:
        return _service.report_for_application(fingerprint, session_id=session_id)
    except RegressionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MalformedKnowledgeEvidenceError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.details},
        ) from exc


@router.get(
    "/bridge/regression/sessions/{session_id}",
    response_model=CompatibilityRegressionReport,
    tags=["Regression"],
)
def regression_for_session(session_id: str) -> CompatibilityRegressionReport:
    try:
        return _service.report_for_session(session_id)
    except RegressionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MalformedKnowledgeEvidenceError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.details},
        ) from exc
