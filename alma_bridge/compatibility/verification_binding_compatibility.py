from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional, Tuple

from alma_bridge.compatibility.expected_verification_contract import (
    ExpectedVerificationContract,
)
from alma_bridge.compatibility.profile_fingerprints import (
    build_verification_binding_key,
    build_verification_binding_payload,
)
from alma_bridge.compatibility.profile_shadow_reasons import EligibilityReasonCode

# Registered semantic policy relationships (explicit only).
SEMANTIC_POLICY_COMPATIBILITY: dict[tuple[str, str], frozenset[str]] = {
    # bridge_aggregate_v1 launcher checks cover wine_gui when only process_survives required
    ("bridge_aggregate_v1", "wine_gui_process_v1"): frozenset({"wine_gui"}),
}

KNOWN_POLICIES = frozenset(
    {
        "bridge_aggregate_v1",
        "wine_gui_process_v1",
    }
)

KNOWN_PROGRAM_KINDS = frozenset(
    {
        "native_script",
        "pe_windows_gui",
        "pe_windows",
        "pe_electron_launcher",
        "pe_installer",
    }
)


@dataclass(frozen=True)
class VerificationBindingCompatibilityResult:
    compatible: bool
    reason_codes: List[str] = field(default_factory=list)
    binding_key_match: bool = False

    @property
    def aggregate_incompatible(self) -> bool:
        return bool(self.reason_codes)


def _parse_required_checks(verification: Mapping[str, Any], profile: Mapping[str, Any]) -> List[str]:
    raw = verification.get("required_checks_json")
    if raw:
        try:
            parsed = json.loads(str(raw))
            if isinstance(parsed, list):
                return sorted(str(c) for c in parsed)
        except json.JSONDecodeError:
            pass
    policy_checks = (verification.get("success_policy") or {}).get("required_checks")
    if isinstance(policy_checks, dict):
        for values in policy_checks.values():
            if isinstance(values, list):
                return sorted(str(c) for c in values)
    return []


def _version_compatible(stored_version: str, expected_version: str) -> bool:
    return stored_version == expected_version


def _checks_cover_expected(stored_checks: List[str], expected_checks: List[str]) -> bool:
    stored = set(stored_checks)
    return set(expected_checks).issubset(stored)


def evaluate_verification_binding_compatibility(
    *,
    profile_bundle: Mapping[str, Any],
    expected: ExpectedVerificationContract,
) -> VerificationBindingCompatibilityResult:
    profile = profile_bundle["profile"]
    verification = profile_bundle.get("verification") or {}
    program_fp = profile_bundle.get("program") or {}

    stored_policy_id = str(verification.get("policy_id") or profile.get("policy_id") or "")
    stored_policy_version = str(
        verification.get("policy_version") or profile.get("policy_version") or ""
    )
    stored_program_kind = str(program_fp.get("program_kind") or "")
    stored_required = _parse_required_checks(verification, profile)
    stored_binding = str(profile.get("verification_binding_key") or "")

    reasons: List[str] = []

    if (
        stored_program_kind in KNOWN_PROGRAM_KINDS
        and expected.program_kind in KNOWN_PROGRAM_KINDS
        and stored_program_kind != expected.program_kind
    ):
        reasons.append(EligibilityReasonCode.VERIFICATION_PHASE_MISMATCH.value)

    if stored_policy_id not in KNOWN_POLICIES:
        reasons.append(EligibilityReasonCode.VERIFICATION_POLICY_UNKNOWN.value)

    exact_policy = stored_policy_id == expected.policy_id
    semantic_key = (expected.policy_id, stored_policy_id)
    semantic_ok = (
        semantic_key in SEMANTIC_POLICY_COMPATIBILITY
        and expected.phase in SEMANTIC_POLICY_COMPATIBILITY[semantic_key]
    )

    if not exact_policy and not semantic_ok:
        reasons.append(EligibilityReasonCode.VERIFICATION_POLICY_ID_MISMATCH.value)
    elif not _version_compatible(stored_policy_version, expected.policy_version):
        reasons.append(EligibilityReasonCode.VERIFICATION_POLICY_VERSION_INCOMPATIBLE.value)

    if stored_required and not _checks_cover_expected(stored_required, expected.required_checks):
        reasons.append(EligibilityReasonCode.REQUIRED_CHECKS_MISMATCH.value)

    binding_match = False
    if (exact_policy or semantic_ok) and stored_binding and stored_required:
        reconstructed = build_verification_binding_key(
            build_verification_binding_payload(
                policy_id=stored_policy_id,
                policy_version=stored_policy_version,
                required_checks=stored_required,
            )
        )
        binding_match = stored_binding == reconstructed
        if not binding_match:
            reasons.append(EligibilityReasonCode.VERIFIER_VERSION_INCOMPATIBLE.value)

    if reasons:
        reasons.append(EligibilityReasonCode.VERIFICATION_BINDING_INCOMPATIBLE.value)

    reasons = sorted(set(reasons))
    compatible = not reasons
    return VerificationBindingCompatibilityResult(
        compatible=compatible,
        reason_codes=reasons,
        binding_key_match=binding_match,
    )
