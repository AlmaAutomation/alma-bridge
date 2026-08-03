"""Evidence timeline hooks for native lab lifecycle events."""

from __future__ import annotations

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.evidence.service import EvidenceService


def _service() -> EvidenceService:
    return EvidenceService.shared()


def _first_bundle_id() -> str | None:
    try:
        from alma_bridge.evidence.repository import EvidenceRepository

        repo = EvidenceRepository()
        ids = repo.list_all_bundle_ids()
        return ids[0] if ids else None
    except Exception:
        return None


def on_engineering_work_item_created(work_item_id: str, work_item_digest: str) -> None:
    try:
        bundle_id = _first_bundle_id()
        if not bundle_id:
            return
        _service().record_engineering_work_item_created(bundle_id, work_item_id, work_item_digest)
    except Exception:
        pass


def on_engineering_work_item_accepted(work_item_id: str, event_digest: str) -> None:
    try:
        bundle_id = _first_bundle_id()
        if not bundle_id:
            return
        _service().record_engineering_work_item_accepted(bundle_id, work_item_id, event_digest)
    except Exception:
        pass


def on_implementation_evidence_attached(
    work_item_id: str, reference_id: str, artifact_id: str
) -> None:
    try:
        bundle_id = _first_bundle_id()
        if not bundle_id:
            return
        digest = sha256_v1({"work_item_id": work_item_id, "reference_id": reference_id})
        _service().record_implementation_evidence_attached(
            bundle_id, work_item_id, reference_id, digest
        )
    except Exception:
        pass


def on_behavior_tests_completed(work_item_id: str, test_digest: str) -> None:
    try:
        bundle_id = _first_bundle_id()
        if not bundle_id:
            return
        _service().record_behavior_tests_completed(bundle_id, work_item_id, test_digest)
    except Exception:
        pass


def on_verification_requested(work_item_id: str, request_digest: str) -> None:
    try:
        bundle_id = _first_bundle_id()
        if not bundle_id:
            return
        _service().record_verification_requested(bundle_id, work_item_id, request_digest)
    except Exception:
        pass


def on_certification_requested(work_item_id: str, request_digest: str) -> None:
    try:
        bundle_id = _first_bundle_id()
        if not bundle_id:
            return
        _service().record_certification_requested(bundle_id, work_item_id, request_digest)
    except Exception:
        pass


def on_engineering_work_item_completed(work_item_id: str, completion_digest: str) -> None:
    try:
        bundle_id = _first_bundle_id()
        if not bundle_id:
            return
        _service().record_engineering_work_item_completed(
            bundle_id, work_item_id, completion_digest
        )
    except Exception:
        pass


def on_engineering_work_item_superseded(
    work_item_id: str, successor_id: str, supersede_digest: str
) -> None:
    try:
        bundle_id = _first_bundle_id()
        if not bundle_id:
            return
        _service().record_engineering_work_item_superseded(
            bundle_id, work_item_id, successor_id, supersede_digest
        )
    except Exception:
        pass
