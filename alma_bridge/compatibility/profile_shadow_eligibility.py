from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional

from alma_bridge.compatibility.expected_verification_contract import (
    ExpectedVerificationContract,
)
from alma_bridge.compatibility.profile_shadow_drift import predict_bridge_drift
from alma_bridge.compatibility.profile_shadow_models import (
    DriftDimension,
    ShadowCandidateEvaluation,
)
from alma_bridge.compatibility.profile_shadow_reasons import (
    ACTIVE_REUSE_TRUST_STATES,
    DIAGNOSTIC_ONLY_LIFECYCLE_STATES,
    SHADOW_ONLY_TRUST_STATES,
    WINNER_BLOCKING_REASONS,
    WINNER_LIFECYCLE_STATES,
    EligibilityReasonCode,
)
from alma_bridge.compatibility.verification_binding_compatibility import (
    evaluate_verification_binding_compatibility,
)

SUPPORTED_MANIFEST_SCHEMA = "bridge_manifest_v1"


def _trust_category(
    trust_state: str,
    lifecycle_state: str,
    rejection_codes: List[str],
) -> str:
    if rejection_codes:
        return "rejected"
    if lifecycle_state in DIAGNOSTIC_ONLY_LIFECYCLE_STATES:
        return "rejected"
    if trust_state in SHADOW_ONLY_TRUST_STATES:
        return "shadow_observation_only"
    if trust_state in ACTIVE_REUSE_TRUST_STATES and lifecycle_state in WINNER_LIFECYCLE_STATES:
        return "eligible_for_future_active_reuse"
    return "shadow_observation_only"


def _winner_selectable(
    trust_category: str,
    lifecycle_state: str,
    rejection_codes: List[str],
    has_active_invalidation: bool,
) -> bool:
    if rejection_codes:
        return False
    if has_active_invalidation:
        return False
    if lifecycle_state not in WINNER_LIFECYCLE_STATES:
        return False
    return trust_category == "eligible_for_future_active_reuse"


def evaluate_candidate_eligibility(
    *,
    profile_bundle: Mapping[str, Any],
    program_identity_key: str,
    host_compatibility_class_id: str,
    host_payload: Mapping[str, Any],
    expected_verification: ExpectedVerificationContract,
    required_capabilities: Optional[List[str]] = None,
    active_invalidations: Optional[List[Mapping[str, Any]]] = None,
    wine_prefix: Optional[str] = None,
) -> ShadowCandidateEvaluation:
    profile = profile_bundle["profile"]
    host_fp = profile_bundle.get("host") or {}
    program_fp = profile_bundle.get("program") or {}
    bridge = profile_bundle.get("bridge") or {}
    artifacts = profile_bundle.get("artifacts") or []

    profile_id = str(profile["profile_id"])
    lifecycle_state = str(profile["lifecycle_state"])
    trust_state = str(profile["trust_state"])

    rejection_codes: List[str] = []
    scoped_invalidations: List[str] = []

    if lifecycle_state in DIAGNOSTIC_ONLY_LIFECYCLE_STATES:
        code = (
            EligibilityReasonCode.RETIRED_PROFILE_DIAGNOSTIC_ONLY.value
            if lifecycle_state == "RETIRED"
            else EligibilityReasonCode.INVALIDATED_PROFILE_DIAGNOSTIC_ONLY.value
        )
        rejection_codes.append(code)

    if str(program_fp.get("program_identity_key") or "") != program_identity_key:
        rejection_codes.append(EligibilityReasonCode.PROGRAM_IDENTITY_MISMATCH.value)

    stored_host_id = str(host_fp.get("host_compatibility_class_id") or "")
    if stored_host_id != host_compatibility_class_id:
        rejection_codes.append(EligibilityReasonCode.HOST_ARCH_MISMATCH.value)

    stored_host = json.loads(host_fp.get("host_class_json") or "{}")
    if stored_host.get("os_family") and stored_host.get("os_family") != host_payload.get("os_family"):
        rejection_codes.append(EligibilityReasonCode.OS_FAMILY_MISMATCH.value)
    if stored_host.get("host_arch") and stored_host.get("host_arch") != host_payload.get("host_arch"):
        rejection_codes.append(EligibilityReasonCode.HOST_ARCH_MISMATCH.value)

    current_wine_major = host_payload.get("wine_major")
    stored_wine_major = stored_host.get("wine_major")
    if stored_wine_major and current_wine_major and stored_wine_major != current_wine_major:
        rejection_codes.append(EligibilityReasonCode.WINE_MAJOR_INCOMPATIBLE.value)

    if required_capabilities:
        stored_caps = set(json.loads(host_fp.get("capability_set_json") or "[]"))
        for cap in required_capabilities:
            if cap not in stored_caps:
                rejection_codes.append(EligibilityReasonCode.REQUIRED_CAPABILITY_MISSING.value)
                break

    for inv in active_invalidations or []:
        scope = str(inv.get("scope") or "")
        if scope == "host_class" and str(inv.get("scope_key") or "") == host_compatibility_class_id:
            rejection_codes.append(EligibilityReasonCode.ACTIVE_HOST_CLASS_INVALIDATION.value)
            scoped_invalidations.append(str(inv.get("invalidation_id") or ""))
        if scope == "program" and str(inv.get("scope_key") or "") == program_identity_key:
            rejection_codes.append(EligibilityReasonCode.ACTIVE_PROGRAM_INVALIDATION.value)
            scoped_invalidations.append(str(inv.get("invalidation_id") or ""))

    manifest = json.loads(bridge.get("manifest_json") or "{}")
    if manifest.get("schema") and manifest.get("schema") != SUPPORTED_MANIFEST_SCHEMA:
        rejection_codes.append(EligibilityReasonCode.MANIFEST_SCHEMA_UNSUPPORTED.value)

    binding_result = evaluate_verification_binding_compatibility(
        profile_bundle=profile_bundle,
        expected=expected_verification,
    )
    binding_compatible = binding_result.compatible
    rejection_codes.extend(binding_result.reason_codes)

    if not str(profile.get("bridge_family_key") or ""):
        rejection_codes.append(EligibilityReasonCode.UNSUPPORTED_BRIDGE_FAMILY.value)

    for artifact in artifacts:
        checksum = str(artifact.get("checksum_sha256") or "")
        acquisition = str(artifact.get("acquisition_method") or "")
        if acquisition in {"download", "imported"} and not checksum:
            rejection_codes.append(EligibilityReasonCode.ARTIFACT_CHECKSUM_MISSING.value)
        if str(artifact.get("signature_status") or "") == "untrusted":
            rejection_codes.append(EligibilityReasonCode.ARTIFACT_PROVENANCE_FAILURE.value)

    if lifecycle_state not in WINNER_LIFECYCLE_STATES | DIAGNOSTIC_ONLY_LIFECYCLE_STATES:
        rejection_codes.append(EligibilityReasonCode.INVALID_LIFECYCLE_STATE.value)

    rejection_codes = sorted(set(rejection_codes))
    blocking = [c for c in rejection_codes if c in {r.value for r in WINNER_BLOCKING_REASONS}]
    eligibility_status = "rejected" if blocking else "eligible"
    trust_cat = _trust_category(trust_state, lifecycle_state, blocking)
    has_active_inv = bool(scoped_invalidations)

    drift_dims, drift_result = predict_bridge_drift(
        profile_manifest=manifest,
        wine_prefix=wine_prefix,
        launcher_file_hash=manifest.get("launcher_file_hash"),
    )

    return ShadowCandidateEvaluation(
        profile_id=profile_id,
        profile_revision=int(profile["profile_revision"]),
        lifecycle_state=lifecycle_state,
        trust_state=trust_state,
        eligibility_status=eligibility_status,
        trust_category=trust_cat,
        rejection_reason_codes=rejection_codes,
        scoped_invalidations_applied=scoped_invalidations,
        host_match_dimensions={
            "program_identity_key_match": program_fp.get("program_identity_key") == program_identity_key,
            "host_compatibility_class_id_match": stored_host_id == host_compatibility_class_id,
            "os_family_match": stored_host.get("os_family") == host_payload.get("os_family"),
            "host_arch_match": stored_host.get("host_arch") == host_payload.get("host_arch"),
            "wine_major_match": stored_wine_major == current_wine_major,
        },
        bridge_family_match_dimensions={
            "bridge_family_key": profile.get("bridge_family_key"),
            "strategy_id": profile.get("strategy_id"),
            "bridge_manifest_hash": profile.get("bridge_manifest_hash"),
        },
        verification_binding_compatible=binding_compatible,
        drift_dimensions=drift_dims,
        drift_prediction_result=drift_result,
        winner_selectable=_winner_selectable(
            trust_cat, lifecycle_state, blocking, has_active_inv
        ),
    )
