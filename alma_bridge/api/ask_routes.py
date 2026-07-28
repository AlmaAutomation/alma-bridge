"""Ask Alma evidence-grounded Q&A routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from alma_bridge.ask.models import AskAlmaAnswer, AskAlmaNotFoundError, AskAlmaQuestion, AskAlmaValidationError
from alma_bridge.ask.service import AskAlmaService

router = APIRouter()
_service = AskAlmaService()


@router.post("/bridge/ask", response_model=AskAlmaAnswer, tags=["AskAlma"])
def ask_alma(payload: AskAlmaQuestion) -> AskAlmaAnswer:
    try:
        return _service.ask(payload)
    except AskAlmaNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AskAlmaValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.details},
        ) from exc
