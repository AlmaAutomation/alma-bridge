from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Union

from alma_bridge.compatibility.profile_candidate import build_profile_candidate_snapshot
from alma_bridge.compatibility.profile_lineage import promote_candidate_snapshot
from alma_bridge.compatibility.profile_metrics import (
    increment_profile_counter,
    log_profile_event,
)
from alma_bridge.compatibility.profile_models import ProfileCandidateSnapshot
from alma_bridge.compatibility.profile_store import (
    load_candidate_snapshot,
    persist_candidate_snapshot,
    record_candidate_event,
    record_creation_event,
)
from alma_bridge.config import settings
from alma_bridge.execution.preflight import read_wine_windows_version
from alma_bridge.schemas.models import AttemptRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VerifiedAttemptInputs:
    """Immutable verified-attempt context for candidate snapshot construction."""

    session_id: str
    file_path: str
    executable_hash: str
    hardware: Mapping[str, Any]
    record: AttemptRecord
    verification_payload: Mapping[str, Any]
    applied_remediation_ids: Optional[List[Optional[str]]] = None
    wine_version: Optional[str] = None
    windows_version: Optional[str] = None
    prefix_architecture: str = "win64"
    winetricks_components: Optional[List[str]] = None
    wrapper_versions: Optional[Mapping[str, str]] = None
    config_hashes: Optional[Mapping[str, str]] = None
    launcher_file_hash: Optional[str] = None
    external_artifacts: Optional[List[Dict[str, Any]]] = None


def _prefix_context(record: AttemptRecord) -> tuple[Optional[str], Optional[str]]:
    prefix = (record.env or {}).get("WINEPREFIX")
    if not prefix:
        return None, None
    try:
        return prefix, read_wine_windows_version(prefix)
    except Exception:  # noqa: BLE001
        return prefix, None


class ProfileCandidateService:
    """Build and persist immutable profile candidate snapshots."""

    @staticmethod
    def build_snapshot(inputs: VerifiedAttemptInputs) -> ProfileCandidateSnapshot:
        _, windows_version = _prefix_context(inputs.record)
        return build_profile_candidate_snapshot(
            session_id=inputs.session_id,
            attempt_number=inputs.record.attempt_number,
            file_path=inputs.file_path,
            executable_hash=inputs.executable_hash,
            hardware=inputs.hardware,
            strategy_id=inputs.record.strategy_id,
            runtime=inputs.record.runtime,
            remediation_id=inputs.record.remediation_id,
            env=inputs.record.env or {},
            verification_payload=dict(inputs.verification_payload),
            phase=inputs.record.phase,
            applied_remediation_ids=inputs.applied_remediation_ids,
            wine_version=inputs.wine_version,
            windows_version=inputs.windows_version or windows_version,
            prefix_architecture=inputs.prefix_architecture,
            winetricks_components=inputs.winetricks_components,
            wrapper_versions=inputs.wrapper_versions,
            config_hashes=inputs.config_hashes,
            launcher_file_hash=inputs.launcher_file_hash,
            external_artifacts=inputs.external_artifacts,
            path_alias=inputs.file_path,
        )

    @staticmethod
    def persist_snapshot(snapshot: ProfileCandidateSnapshot) -> str:
        candidate_id = persist_candidate_snapshot(snapshot)
        record_candidate_event(
            session_id=snapshot.source_session_id,
            attempt_number=snapshot.source_attempt_number,
            outcome="persisted",
            candidate_id=candidate_id,
        )
        increment_profile_counter("profile_candidate_persisted")
        log_profile_event(
            "profile_candidate_persisted",
            session_id=snapshot.source_session_id,
            candidate_id=candidate_id,
            lineage_key=snapshot.profile_lineage_key,
        )
        return candidate_id

    @classmethod
    def persist_from_verified(cls, inputs: VerifiedAttemptInputs) -> Optional[str]:
        if not settings.compatibility_profiles_enabled:
            return None
        try:
            snapshot = cls.build_snapshot(inputs)
            return cls.persist_snapshot(snapshot)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "profile candidate snapshot persistence failed session=%s attempt=%s",
                inputs.session_id,
                inputs.record.attempt_number,
            )
            record_candidate_event(
                session_id=inputs.session_id,
                attempt_number=inputs.record.attempt_number,
                outcome="persist_failed",
                error=str(exc),
            )
            increment_profile_counter("profile_candidate_persist_failed")
            log_profile_event(
                "profile_candidate_persist_failed",
                session_id=inputs.session_id,
                attempt_number=inputs.record.attempt_number,
                error=str(exc),
            )
            return None


class ProfileCreationService:
    """Promote persisted candidate snapshots into compatibility profiles."""

    @staticmethod
    def promote(
        source: Union[str, ProfileCandidateSnapshot],
    ) -> Optional[str]:
        if not settings.compatibility_profiles_enabled:
            return None
        if not settings.compatibility_profile_creation_enabled:
            return None

        snapshot: Optional[ProfileCandidateSnapshot]
        if isinstance(source, str):
            snapshot = load_candidate_snapshot(source)
            if not snapshot:
                record_creation_event(
                    session_id="unknown",
                    outcome="promote_failed",
                    candidate_id=source,
                    error="candidate_not_found",
                )
                increment_profile_counter("profile_creation_failed")
                return None
        else:
            snapshot = source

        try:
            profile_id, outcome = promote_candidate_snapshot(snapshot)
            increment_profile_counter(f"profile_{outcome}")
            log_profile_event(
                f"profile_{outcome}",
                session_id=snapshot.source_session_id,
                candidate_id=snapshot.candidate_id,
                profile_id=profile_id,
                idempotency_key=snapshot.idempotency_key,
            )
            return profile_id
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "profile creation failed session=%s candidate=%s",
                snapshot.source_session_id,
                snapshot.candidate_id,
            )
            record_creation_event(
                session_id=snapshot.source_session_id,
                outcome="promote_failed",
                candidate_id=snapshot.candidate_id,
                error=str(exc),
                idempotency_key=snapshot.idempotency_key,
            )
            increment_profile_counter("profile_creation_failed")
            log_profile_event(
                "profile_creation_failed",
                session_id=snapshot.source_session_id,
                candidate_id=snapshot.candidate_id,
                error=str(exc),
            )
            return None
