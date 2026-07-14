from __future__ import annotations

from typing import Any, Dict, List, Optional

from alma_bridge.compatibility.profile_candidate import build_profile_candidate_snapshot
from alma_bridge.compatibility.profile_fingerprints import (
    BRIDGE_FAMILY_SCHEMA,
    build_bridge_family_key,
    build_bridge_family_payload,
    build_idempotency_key,
    build_profile_lineage_key,
    build_program_identity_key,
    build_program_identity_payload,
    build_verification_binding_key,
    build_verification_binding_payload,
)
from alma_bridge.compatibility.profile_host_class import (
    build_host_compatibility_class_id,
    build_host_compatibility_class_payload,
)
from alma_bridge.compatibility.profile_models import ProfileCandidateSnapshot
from alma_bridge.schemas.models import AttemptRecord, ExecutionMode


def sample_hardware() -> Dict[str, Any]:
    return {
        "architecture": "x86_64",
        "distribution": {"id": "ubuntu", "id_like": "debian"},
        "capabilities": {"container": True, "gpu": False},
        "gpu": {"vendor": "nvidia", "driver": "550.54.14"},
    }


def sample_verification_payload() -> Dict[str, Any]:
    return {
        "success_policy": {
            "policy_id": "bridge_aggregate_v1",
            "policy_version": "1.0.0",
            "required_checks": {"native": ["exit_code_zero"]},
        },
        "checks": [
            {
                "check_kind": "exit_code_zero",
                "passed": True,
                "verifier_id": "exit_code",
                "verifier_version": "1",
            }
        ],
        "confidence": 0.95,
        "evidence": ["exit_code_zero"],
    }


def sample_wine_gui_verification_payload() -> Dict[str, Any]:
    return {
        "success_policy": {
            "policy_id": "wine_gui_process_v1",
            "policy_version": "1.0.0",
            "required_checks": {"wine_gui": ["process_survives", "target_process_identity"]},
        },
        "checks": [
            {
                "check_kind": "process_survives",
                "passed": True,
                "verifier_id": "wine_gui_process",
                "verifier_version": "1",
            },
            {
                "check_kind": "target_process_identity",
                "passed": True,
                "verifier_id": "wine_gui_process",
                "verifier_version": "1",
            },
        ],
        "confidence": 0.95,
        "evidence": ["process_survives", "target_process_identity"],
    }


def build_test_snapshot(
    *,
    session_id: str = "sess-1",
    attempt_number: int = 1,
    strategy_id: str = "native_direct",
    runtime: str = "native",
    remediation_id: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    manifest_env: Optional[Dict[str, str]] = None,
    file_path: str = "/tmp/game.sh",
    executable_hash: str = "abc123",
    verification_payload: Optional[Dict[str, Any]] = None,
    phase: str = "native",
) -> ProfileCandidateSnapshot:
    record_env = dict(env or {})
    if manifest_env:
        record_env.update(manifest_env)
    return build_profile_candidate_snapshot(
        session_id=session_id,
        attempt_number=attempt_number,
        file_path=file_path,
        executable_hash=executable_hash,
        hardware=sample_hardware(),
        strategy_id=strategy_id,
        runtime=runtime,
        remediation_id=remediation_id,
        env=record_env,
        verification_payload=verification_payload or sample_verification_payload(),
        phase=phase,
    )


def sample_attempt_record(**overrides: Any) -> AttemptRecord:
    base = {
        "attempt_number": 1,
        "strategy_id": "native_direct",
        "remediation_id": None,
        "runtime": "native",
        "command": ["bash", "/tmp/game.sh"],
        "env": {},
        "mode": ExecutionMode.HOST,
        "success": True,
        "phase": "native",
    }
    base.update(overrides)
    return AttemptRecord(**base)
