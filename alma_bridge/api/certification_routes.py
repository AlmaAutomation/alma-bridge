"""Read-only HTTP routes for Runtime Certification Platform."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from alma_bridge.certification.errors import BehaviorNotFoundError
from alma_bridge.certification.models import CERTIFICATION_SCHEMA_VERSION
from alma_bridge.certification.service import CertificationService

router = APIRouter()


def _service() -> CertificationService:
    return CertificationService.shared()


@router.get("/bridge/certification/behaviors", tags=["Certification"])
def list_behavior_certifications():
    """List behavior certifications (read-only)."""
    certs = _service().list_behavior_certifications()
    return {
        "schema_version": CERTIFICATION_SCHEMA_VERSION,
        "count": len(certs),
        "behaviors": [c.model_dump(mode="json") for c in certs],
    }


@router.get(
    "/bridge/certification/behaviors/{capability_id}/{behavior_id}",
    tags=["Certification"],
)
def get_behavior_certification(capability_id: str, behavior_id: str):
    """Full certification profile for one behavior (read-only)."""
    try:
        cert = _service().get_behavior_certification(capability_id, behavior_id)
    except BehaviorNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return cert.model_dump(mode="json")
