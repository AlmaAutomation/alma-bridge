from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from alma_bridge.compatibility.profile_fingerprints import (
    BRIDGE_MANIFEST_SCHEMA,
    build_bridge_family_key,
    build_bridge_family_payload,
    build_bridge_manifest_hash,
    build_idempotency_key,
    build_profile_lineage_key,
    build_program_identity_key,
    build_program_identity_payload,
    build_verification_binding_key,
    build_verification_binding_payload,
    bridge_architecture_class,
    protocol_family_from_flags,
    runtime_family_from_runtime,
    sorted_map,
)
from alma_bridge.compatibility.profile_host_class import (
    build_host_compatibility_class_id,
    build_host_compatibility_class_payload,
)
from alma_bridge.compatibility.profile_models import (
    CANDIDATE_SCHEMA_VERSION,
    ProfileCandidateSnapshot,
    new_candidate_id,
)
from alma_bridge.compatibility.program_kind import classify_program_kind
from alma_bridge.config import settings
from alma_bridge.execution.runner import file_hash


def _stable_env(env: Mapping[str, str]) -> Dict[str, str]:
    # WINEPREFIX is audit-only (prefix_reference); disposable path must not affect manifest identity.
    excluded = {
        "PWD",
        "OLDPWD",
        "SHLVL",
        "_",
        "TMPDIR",
        "TEMP",
        "TMP",
        "WINEPREFIX",
        "WINEDEBUG",
    }
    return {
        str(k): str(v)
        for k, v in sorted(env.items(), key=lambda item: str(item[0]))
        if str(k) not in excluded and not str(k).startswith("ALMA_SESSION_")
    }


def _remediation_protocol_from_attempt(
    *,
    remediation_id: Optional[str],
    applied_remediation_ids: Optional[List[Optional[str]]] = None,
) -> List[Dict[str, str]]:
    protocol: List[Dict[str, str]] = []
    seen: set[str] = set()
    for rid in applied_remediation_ids or []:
        if rid and rid not in seen:
            protocol.append({"id": str(rid), "version": "1"})
            seen.add(str(rid))
    if remediation_id and str(remediation_id) not in seen:
        protocol.append({"id": str(remediation_id), "version": "1"})
    return protocol


def build_bridge_manifest(
    *,
    runtime: str,
    strategy_id: str,
    windows_version: Optional[str],
    prefix_architecture: str,
    remediation_protocol: List[Dict[str, str]],
    env: Mapping[str, str],
    winetricks_components: Optional[List[str]] = None,
    dll_overrides: Optional[Mapping[str, str]] = None,
    wrapper_versions: Optional[Mapping[str, str]] = None,
    config_hashes: Optional[Mapping[str, str]] = None,
    launcher_file_hash: Optional[str] = None,
    external_artifacts: Optional[List[Dict[str, Any]]] = None,
    base_runtime_version_family: Optional[str] = None,
    manifest_capture_version: Optional[str] = None,
    component_capture_complete: bool = False,
) -> Dict[str, Any]:
    manifest: Dict[str, Any] = {
        "schema": BRIDGE_MANIFEST_SCHEMA,
        "base_runtime": {
            "kind": runtime_family_from_runtime(runtime),
            "version_family": base_runtime_version_family,
        },
        "prefix_architecture": prefix_architecture,
        "windows_version": windows_version,
        "installed_components": sorted(str(c) for c in (winetricks_components or [])),
        "dll_overrides": sorted_map(dll_overrides),
        "environment": _stable_env(env),
        "wrapper_versions": sorted_map(wrapper_versions),
        "remediation_protocol": sorted(
            remediation_protocol,
            key=lambda item: (item.get("id") or "", item.get("version") or ""),
        ),
        "config_file_hashes": sorted_map(config_hashes),
        "launcher_file_hash": launcher_file_hash,
        "external_artifacts": list(external_artifacts or []),
    }
    if manifest_capture_version:
        manifest["manifest_capture_version"] = manifest_capture_version
        manifest["component_capture_complete"] = component_capture_complete
    return manifest


def build_profile_candidate_snapshot(
    *,
    session_id: str,
    attempt_number: int,
    file_path: str,
    executable_hash: str,
    hardware: Mapping[str, Any],
    strategy_id: str,
    runtime: str,
    remediation_id: Optional[str],
    env: Mapping[str, str],
    verification_payload: Mapping[str, Any],
    phase: str,
    applied_remediation_ids: Optional[List[Optional[str]]] = None,
    wine_version: Optional[str] = None,
    windows_version: Optional[str] = None,
    prefix_architecture: str = "win64",
    winetricks_components: Optional[List[str]] = None,
    wrapper_versions: Optional[Mapping[str, str]] = None,
    config_hashes: Optional[Mapping[str, str]] = None,
    launcher_file_hash: Optional[str] = None,
    external_artifacts: Optional[List[Dict[str, Any]]] = None,
    path_alias: Optional[str] = None,
    manifest_capture_version: Optional[str] = None,
    component_capture_complete: bool = False,
    dll_overrides: Optional[Mapping[str, str]] = None,
) -> ProfileCandidateSnapshot:
    kind = classify_program_kind(
        file_path,
        host_arch=str(hardware.get("architecture") or "x86_64"),
    )
    program_identity_payload = build_program_identity_payload(
        executable_hash=executable_hash,
        executable_format=str(kind.get("binary_format") or "unknown"),
        architecture=str(hardware.get("architecture") or "unknown"),
        program_kind=str(kind.get("program_kind") or "unknown"),
        product_version=None,
        bundled_hashes=(
            {str(file_path): launcher_file_hash}
            if launcher_file_hash
            else None
        ),
    )
    program_identity_key = build_program_identity_key(program_identity_payload)

    host_payload = build_host_compatibility_class_payload(
        hardware,
        wine_version=wine_version,
        program_needs_gpu=bool(kind.get("needs_gui")),
    )
    host_class_id = build_host_compatibility_class_id(host_payload)

    runtime_family = runtime_family_from_runtime(runtime)
    protocol_family = protocol_family_from_flags(
        installer=bool(kind.get("is_installer")),
        electron=bool(kind.get("is_electron")),
        gui_launcher=phase == "launcher",
        wine_gui=phase == "wine_gui",
    )
    bridge_family_payload = build_bridge_family_payload(
        strategy_id=strategy_id,
        runtime_family=runtime_family,
        program_kind=str(kind.get("program_kind") or "unknown"),
        protocol_family=protocol_family,
        bridge_architecture_class=bridge_architecture_class(
            runtime_family=runtime_family,
            program_kind=str(kind.get("program_kind") or "unknown"),
            executable_format=str(kind.get("binary_format") or "unknown"),
        ),
    )
    bridge_family_key = build_bridge_family_key(bridge_family_payload)

    remediation_protocol = _remediation_protocol_from_attempt(
        remediation_id=remediation_id,
        applied_remediation_ids=applied_remediation_ids,
    )
    manifest = build_bridge_manifest(
        runtime=runtime,
        strategy_id=strategy_id,
        windows_version=windows_version,
        prefix_architecture=prefix_architecture,
        remediation_protocol=remediation_protocol,
        env=env,
        winetricks_components=winetricks_components,
        dll_overrides=dll_overrides,
        wrapper_versions=wrapper_versions,
        config_hashes=config_hashes,
        launcher_file_hash=launcher_file_hash,
        external_artifacts=external_artifacts,
        base_runtime_version_family=wine_version,
        manifest_capture_version=manifest_capture_version,
        component_capture_complete=component_capture_complete,
    )
    manifest_hash = build_bridge_manifest_hash(manifest)

    success_policy = dict(verification_payload.get("success_policy") or {})
    required_checks = [
        str(check.get("check_kind"))
        for check in (verification_payload.get("checks") or [])
        if check.get("passed")
    ]
    if not required_checks:
        required_checks = list(
            (success_policy.get("required_checks") or {}).get(phase, [])
            or (success_policy.get("required_checks") or {}).get("native", [])
        )
    binding_payload = build_verification_binding_payload(
        policy_id=str(success_policy.get("policy_id") or "bridge_aggregate_v1"),
        policy_version=str(success_policy.get("policy_version") or "1.0.0"),
        required_checks=required_checks,
    )
    binding_key = build_verification_binding_key(binding_payload)

    lineage_key = build_profile_lineage_key(
        program_identity_key=program_identity_key,
        host_compatibility_class_id=host_class_id,
        bridge_family_key=bridge_family_key,
        verification_binding_key=binding_key,
    )
    idempotency_key = build_idempotency_key(
        profile_lineage_key=lineage_key,
        bridge_manifest_hash=manifest_hash,
        verification_binding_key=binding_key,
    )

    artifacts = list(external_artifacts or [])
    if path_alias:
        artifacts = artifacts + [
            {
                "artifact_type": "path_alias",
                "name": "observed_path",
                "source": "audit",
                "acquisition_method": "observed",
                "checksum_sha256": file_hash(path_alias) if path_alias else "",
                "path_template": path_alias,
            }
        ]

    return ProfileCandidateSnapshot(
        candidate_id=new_candidate_id(),
        source_session_id=session_id,
        source_attempt_number=attempt_number,
        program_identity_payload=program_identity_payload,
        program_identity_key=program_identity_key,
        host_compatibility_class_payload=host_payload,
        host_compatibility_class_id=host_class_id,
        bridge_family_key=bridge_family_key,
        bridge_family_payload=bridge_family_payload,
        bridge_manifest=manifest,
        bridge_manifest_hash=manifest_hash,
        verification_binding_payload=binding_payload,
        verification_binding_key=binding_key,
        verification_payload=dict(verification_payload),
        artifact_provenance=artifacts,
        strategy_id=strategy_id,
        strategy_version=getattr(settings, "bridge_build", "1"),
        remediation_protocol=remediation_protocol,
        trust_source="locally_verified",
        candidate_schema_version=CANDIDATE_SCHEMA_VERSION,
        profile_lineage_key=lineage_key,
        idempotency_key=idempotency_key,
    )
