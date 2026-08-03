"""Link prediction snapshots to authoritative Bridge verification outcomes."""

from __future__ import annotations

from typing import Optional

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.compatibility_intelligence.models import (
    ACI_CALIBRATION_SCHEMA_VERSION,
    OutcomeLink,
    OutcomeType,
    PredictionSnapshot,
)
from alma_bridge.compatibility_intelligence.calibration_repository import (
    CalibrationRepository,
    _utc_now_iso,
)


OUTCOME_LINK_ENGINE_VERSION = "aci_outcome_link_v1"


def resolve_outcome_type(
    *,
    success: bool,
    verification_result_ref: Optional[str],
    execution_attempted: bool = True,
    provider_ineligible: bool = False,
    blocked_by_policy: bool = False,
    runtime_fault: bool = False,
    verification_inconclusive: bool = False,
) -> OutcomeType:
    if blocked_by_policy:
        return OutcomeType.BLOCKED_BY_POLICY
    if provider_ineligible:
        return OutcomeType.PROVIDER_INELIGIBLE
    if not execution_attempted:
        return OutcomeType.EXECUTION_NOT_ATTEMPTED
    if runtime_fault:
        return OutcomeType.RUNTIME_FAULT
    if verification_inconclusive:
        return OutcomeType.VERIFICATION_INCONCLUSIVE
    if not verification_result_ref:
        return OutcomeType.UNVERIFIABLE
    if success:
        return OutcomeType.VERIFIED_SUCCESS
    return OutcomeType.VERIFIED_FAILURE


def _binding_valid(snapshot: PredictionSnapshot, *, binary_digest: str, provider_id: str) -> bool:
    if snapshot.binary_digest != binary_digest:
        return False
    if snapshot.provider_id != provider_id:
        return False
    return True


def build_outcome_link(
    snapshot: PredictionSnapshot,
    *,
    session_id: str,
    attempt_id: Optional[int] = None,
    outcome_type: OutcomeType,
    verification_result_ref: Optional[str] = None,
    verified_success: bool = False,
    failure_signature: Optional[str] = None,
    created_at: Optional[str] = None,
) -> OutcomeLink:
    ts = created_at or _utc_now_iso()
    cap_digest = sha256_v1(
        {
            "capability_registry": snapshot.capability_registry_version,
            "api_registry": snapshot.api_registry_version,
            "provider_id": snapshot.provider_id,
            "provider_version": snapshot.provider_version,
        }
    )
    payload = {
        "schema": ACI_CALIBRATION_SCHEMA_VERSION,
        "snapshot_id": snapshot.snapshot_id,
        "session_id": session_id,
        "binary_digest": snapshot.binary_digest,
        "outcome_type": outcome_type.value,
        "created_at": ts,
    }
    outcome_id = sha256_v1(payload)

    return OutcomeLink(
        outcome_id=outcome_id,
        snapshot_id=snapshot.snapshot_id,
        session_id=session_id,
        attempt_id=attempt_id,
        binary_digest=snapshot.binary_digest,
        analysis_digest=snapshot.analysis_digest,
        provider_id=snapshot.provider_id,
        provider_version=snapshot.provider_version,
        capability_snapshot_digest=cap_digest,
        outcome_type=outcome_type,
        verification_result_ref=verification_result_ref,
        predicted_eligible=snapshot.predicted_eligible,
        verified_success=verified_success,
        failure_signature=failure_signature,
        created_at=ts,
        engine_version=OUTCOME_LINK_ENGINE_VERSION,
    )


class OutcomeLinkingService:
    """Persist outcome links with binding validation."""

    def __init__(self, repository: Optional[CalibrationRepository] = None) -> None:
        self._repo = repository or CalibrationRepository()

    def link_outcome(
        self,
        snapshot: PredictionSnapshot,
        *,
        session_id: str,
        attempt_id: Optional[int] = None,
        outcome_type: OutcomeType,
        verification_result_ref: Optional[str] = None,
        verified_success: bool = False,
        failure_signature: Optional[str] = None,
    ) -> Optional[OutcomeLink]:
        if not _binding_valid(snapshot, binary_digest=snapshot.binary_digest, provider_id=snapshot.provider_id):
            return None
        link = build_outcome_link(
            snapshot,
            session_id=session_id,
            attempt_id=attempt_id,
            outcome_type=outcome_type,
            verification_result_ref=verification_result_ref,
            verified_success=verified_success,
            failure_signature=failure_signature,
        )
        self._repo.save_json_artifact("outcomes", link.outcome_id, link.model_dump())
        return link

    def get_outcome(self, outcome_id: str) -> Optional[OutcomeLink]:
        data = self._repo.load_json_artifact("outcomes", outcome_id)
        if data:
            return OutcomeLink.model_validate(data)
        return None

    def list_outcomes_for_snapshot(self, snapshot_id: str) -> list[OutcomeLink]:
        results: list[OutcomeLink] = []
        for data in self._repo.list_json_artifacts("outcomes"):
            if data.get("snapshot_id") == snapshot_id:
                results.append(OutcomeLink.model_validate(data))
        return results

    def list_outcomes_for_session(self, session_id: str) -> list[OutcomeLink]:
        results: list[OutcomeLink] = []
        for data in self._repo.list_json_artifacts("outcomes"):
            if data.get("session_id") == session_id:
                results.append(OutcomeLink.model_validate(data))
        return results
