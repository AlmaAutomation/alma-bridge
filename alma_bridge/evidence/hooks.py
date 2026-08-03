"""Integration hooks — append timeline events without changing subsystem authority."""

from __future__ import annotations

from typing import Optional

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.evidence.service import EvidenceService


def _service() -> EvidenceService:
    return EvidenceService.shared()


def on_analysis_created(binary_digest: str, analysis_id: str) -> None:
    try:
        digest = sha256_v1({"analysis_id": analysis_id, "binary_digest": binary_digest})
        _service().record_analysis(binary_digest, analysis_id, digest)
    except Exception:
        pass


def on_prediction_snapshot(binary_digest: str, snapshot_id: str) -> None:
    try:
        bundle = _service().assemble_bundle(binary_digest, persist=True)
        digest = sha256_v1({"snapshot_id": snapshot_id})
        _service().record_prediction(bundle.bundle_id, snapshot_id, digest)
    except Exception:
        pass


def on_execution_started(binary_digest: str, session_id: str) -> None:
    try:
        bundle = _service().assemble_bundle(binary_digest, session_id=session_id, persist=True)
        digest = sha256_v1({"session_id": session_id, "phase": "execution"})
        _service().record_execution(bundle.bundle_id, session_id, digest)
    except Exception:
        pass


def on_verification_completed(
    binary_digest: str,
    session_id: str,
    *,
    verified: bool,
    verification_digest: Optional[str] = None,
) -> None:
    try:
        bundle = _service().assemble_bundle(binary_digest, session_id=session_id, persist=True)
        digest = verification_digest or sha256_v1(
            {"session_id": session_id, "verified": verified}
        )
        _service().record_verification(bundle.bundle_id, session_id, digest, verified)
    except Exception:
        pass


def on_decision_generated(binary_digest: str, plan_id: str, plan_digest: str) -> None:
    try:
        bundle = _service().assemble_bundle(binary_digest, persist=True)
        _service().record_decision(bundle.bundle_id, plan_id, plan_digest)
    except Exception:
        pass


def on_review_submitted(binary_digest: str, review_id: str, review_digest: str) -> None:
    try:
        bundle = _service().assemble_bundle(binary_digest, persist=True)
        _service().record_review(bundle.bundle_id, review_id, review_digest)
    except Exception:
        pass


def on_validation_completed(binary_digest: str, validation_id: str, validation_digest: str) -> None:
    try:
        bundle = _service().assemble_bundle(binary_digest, persist=True)
        _service().record_validation(bundle.bundle_id, validation_id, validation_digest)
    except Exception:
        pass


def on_governance_applied(binary_digest: str, version_id: str, registry_digest: str) -> None:
    try:
        bundle = _service().assemble_bundle(binary_digest, persist=True)
        _service().record_governance(bundle.bundle_id, version_id, registry_digest)
    except Exception:
        pass


def on_expansion_plan_generated(plan_id: str, plan_digest: str) -> None:
    try:
        from alma_bridge.evidence.repository import EvidenceRepository

        repo = EvidenceRepository()
        bundle_ids = repo.list_all_bundle_ids()
        if not bundle_ids:
            return
        _service().record_expansion(bundle_ids[0], plan_id, plan_digest)
    except Exception:
        pass
