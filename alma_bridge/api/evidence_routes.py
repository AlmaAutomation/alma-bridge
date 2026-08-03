"""Read-only HTTP routes for compatibility evidence lifecycle."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from alma_bridge.evidence.service import EvidenceService

router = APIRouter()


def _service() -> EvidenceService:
    return EvidenceService.shared()


@router.get("/bridge/evidence/bundles/{binary_digest}", tags=["Evidence"])
def get_bundle_by_digest(binary_digest: str):
    """Get evidence bundle by binary digest."""
    bundle = _service().get_bundle_by_digest(binary_digest)
    if bundle is None:
        bundle = _service().assemble_bundle(binary_digest, persist=True)
    return bundle.model_dump(mode="json")


@router.get("/bridge/evidence/applications/{fingerprint}", tags=["Evidence"])
def get_bundle_by_fingerprint(fingerprint: str):
    """Get evidence bundle by application fingerprint."""
    bundle = _service().get_bundle_by_fingerprint(fingerprint)
    if bundle is None:
        bundle = _service().assemble_bundle(fingerprint, persist=True)
    return bundle.model_dump(mode="json")


@router.get("/bridge/evidence/bundles/{bundle_id}/timeline", tags=["Evidence"])
def get_bundle_timeline(bundle_id: str):
    """Immutable lifecycle timeline for a bundle."""
    events = _service().get_timeline(bundle_id)
    return {
        "bundle_id": bundle_id,
        "event_count": len(events),
        "events": [event.model_dump(mode="json") for event in events],
    }


@router.get("/bridge/evidence/bundles/{bundle_id}/history", tags=["Evidence"])
def get_bundle_history(bundle_id: str):
    """Historical bundle versions for replay."""
    versions = _service().get_history(bundle_id)
    if not versions:
        from alma_bridge.evidence.queries import EvidenceQueries

        bundle = EvidenceQueries().by_bundle_id(bundle_id)
        if bundle is None:
            raise HTTPException(status_code=404, detail=f"Bundle not found: {bundle_id}")
    return {
        "bundle_id": bundle_id,
        "versions": [v.model_dump(mode="json") for v in versions],
    }


@router.get("/bridge/evidence/platform/health", tags=["Evidence"])
def platform_health():
    """Evidence-backed platform health metrics with sample sizes."""
    report = _service().platform_health()
    return report.model_dump(mode="json")


@router.post("/bridge/evidence/assemble", tags=["Evidence"])
def assemble_bundle(
    file_path: Optional[str] = Query(None),
    binary_digest: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
):
    """Assemble and persist evidence bundle from subsystem artifacts."""
    if file_path:
        bundle = _service().assemble_for_file(file_path, session_id=session_id, persist=True)
    elif binary_digest:
        bundle = _service().assemble_bundle(binary_digest, session_id=session_id, persist=True)
    else:
        raise HTTPException(status_code=400, detail="file_path or binary_digest required")
    return bundle.model_dump(mode="json")
