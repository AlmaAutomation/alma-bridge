from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Mapping, Optional

FINGERPRINT_SCHEMA_VERSION = "fingerprint_schema_v1"
PROGRAM_IDENTITY_SCHEMA = "program_identity_v1"
BRIDGE_FAMILY_SCHEMA = "bridge_family_v1"
BRIDGE_MANIFEST_SCHEMA = "bridge_manifest_v1"
VERIFICATION_BINDING_SCHEMA = "verification_binding_v1"
PROFILE_LINEAGE_SCHEMA = "profile_lineage_v1"
PROFILE_IDEMPOTENCY_SCHEMA = "profile_idempotency_v1"


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_v1(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def sorted_map(values: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not values:
        return {}
    return {str(k): values[k] for k in sorted(values, key=str)}


def sorted_list(values: Optional[List[str]]) -> List[str]:
    return sorted(str(v) for v in (values or []))


def build_program_identity_payload(
    *,
    executable_hash: str,
    executable_format: str,
    architecture: str,
    program_kind: str,
    product_version: Optional[str] = None,
    bundled_hashes: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Path-free program identity. Paths are never part of this payload."""
    return {
        "schema": PROGRAM_IDENTITY_SCHEMA,
        "executable_hash": executable_hash,
        "executable_format": executable_format,
        "architecture": architecture,
        "program_kind": program_kind,
        "product_version": product_version,
        "bundled_hashes": sorted_map(bundled_hashes),
        "fingerprint_schema_version": FINGERPRINT_SCHEMA_VERSION,
    }


def build_program_identity_key(payload: Mapping[str, Any]) -> str:
    return sha256_v1(payload)


def build_bridge_family_payload(
    *,
    strategy_id: str,
    runtime_family: str,
    program_kind: str,
    protocol_family: str,
    bridge_architecture_class: str,
) -> Dict[str, Any]:
    """Stable family identity — no exact manifest, versions, env, or remediation versions."""
    return {
        "schema": BRIDGE_FAMILY_SCHEMA,
        "strategy_id": strategy_id,
        "runtime_family": runtime_family,
        "program_kind": program_kind,
        "protocol_family": protocol_family,
        "bridge_architecture_class": bridge_architecture_class,
    }


def build_bridge_family_key(payload: Mapping[str, Any]) -> str:
    return sha256_v1(payload)


def build_verification_binding_payload(
    *,
    policy_id: str,
    policy_version: str,
    required_checks: List[str],
) -> Dict[str, Any]:
    return {
        "schema": VERIFICATION_BINDING_SCHEMA,
        "policy_id": policy_id,
        "policy_version": policy_version,
        "required_checks": sorted_list(required_checks),
    }


def build_verification_binding_key(payload: Mapping[str, Any]) -> str:
    return sha256_v1(payload)


def build_bridge_manifest_hash(manifest: Mapping[str, Any]) -> str:
    return sha256_v1(manifest)


def build_profile_lineage_key(
    *,
    program_identity_key: str,
    host_compatibility_class_id: str,
    bridge_family_key: str,
    verification_binding_key: str,
) -> str:
    return sha256_v1(
        {
            "schema": PROFILE_LINEAGE_SCHEMA,
            "program_identity_key": program_identity_key,
            "host_compatibility_class_id": host_compatibility_class_id,
            "bridge_family_key": bridge_family_key,
            "verification_binding_key": verification_binding_key,
        }
    )


def build_idempotency_key(
    *,
    profile_lineage_key: str,
    bridge_manifest_hash: str,
    verification_binding_key: str,
) -> str:
    return sha256_v1(
        {
            "schema": PROFILE_IDEMPOTENCY_SCHEMA,
            "profile_lineage_key": profile_lineage_key,
            "bridge_manifest_hash": bridge_manifest_hash,
            "verification_binding_key": verification_binding_key,
        }
    )


def runtime_family_from_runtime(runtime: str) -> str:
    if runtime in {"wine", "proton"}:
        return runtime
    if runtime == "native":
        return "native"
    return "unknown"


def protocol_family_from_flags(
    *,
    installer: bool,
    electron: bool,
    gui_launcher: bool,
    wine_gui: bool = False,
) -> str:
    if installer:
        return "installer"
    if electron or gui_launcher:
        return "electron_launcher"
    if wine_gui:
        return "wine_gui"
    return "generic"


def bridge_architecture_class(
    *,
    runtime_family: str,
    program_kind: str,
    executable_format: str,
) -> str:
    if runtime_family == "native":
        return f"native_{executable_format}"
    if runtime_family in {"wine", "proton"}:
        return f"{runtime_family}_{executable_format}_{program_kind}"
    return f"unknown_{executable_format}"
