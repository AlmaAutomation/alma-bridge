"""Read-only Compatibility Knowledge HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from alma_bridge.knowledge.models import (
    CompatibilityKnowledgeProfile,
    KnowledgeNotFoundError,
    MalformedKnowledgeEvidenceError,
)
from alma_bridge.knowledge.service import CompatibilityKnowledgeService

router = APIRouter()
_service = CompatibilityKnowledgeService()


@router.get(
    "/bridge/knowledge/applications/{fingerprint}",
    response_model=CompatibilityKnowledgeProfile,
    tags=["Knowledge"],
)
def knowledge_for_application(fingerprint: str) -> CompatibilityKnowledgeProfile:
    try:
        return _service.profile_for_application(fingerprint)
    except KnowledgeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MalformedKnowledgeEvidenceError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.details},
        ) from exc
