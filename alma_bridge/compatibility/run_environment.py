"""Compatibility run environment capture and deterministic serialization."""

from __future__ import annotations

import platform
from typing import Any, Dict, List, Mapping, Optional

from pydantic import BaseModel, Field, field_validator

from alma_bridge import __version__ as alma_bridge_version
from alma_bridge.compatibility.profile_fingerprints import sha256_v1, sorted_list
from alma_bridge.compatibility.profile_manifest_capture import (
    MANIFEST_CAPTURE_VERSION,
    _detect_prefix_architecture,
)
from alma_bridge.schemas.models import AttemptRecord

RUN_ENVIRONMENT_SCHEMA_VERSION = "compatibility_run_environment_v1"


class CompatibilityRunEnvironment(BaseModel):
    """Immutable host/runtime identity captured once per execution session."""

    schema_version: str = RUN_ENVIRONMENT_SCHEMA_VERSION
    alma_bridge_version: Optional[str] = None
    host_os: Optional[str] = None
    kernel_version: Optional[str] = None
    host_architecture: Optional[str] = None
    wine_version: Optional[str] = None
    wine_architecture: Optional[str] = None
    prefix_id: Optional[str] = None
    prefix_schema_version: Optional[str] = None
    relevant_runtime_identities: List[str] = Field(default_factory=list)
    execution_strategy_version: Optional[str] = None

    @field_validator("relevant_runtime_identities")
    @classmethod
    def _sort_runtime_identities(cls, value: List[str]) -> List[str]:
        return sorted_list(value)

    def to_canonical_dict(self) -> Dict[str, Any]:
        """Deterministic serialization excluding null/absent fields."""
        payload = self.model_dump(mode="json", exclude_none=True)
        if "relevant_runtime_identities" in payload:
            payload["relevant_runtime_identities"] = sorted_list(
                payload["relevant_runtime_identities"]
            )
        return dict(sorted(payload.items()))

    def identity_fingerprint(self) -> str:
        return sha256_v1(self.to_canonical_dict())

    def summary_label(self) -> str:
        parts: List[str] = []
        if self.wine_version:
            parts.append(str(self.wine_version))
        if self.host_os and self.host_architecture:
            parts.append(f"{self.host_os}/{self.host_architecture}")
        elif self.host_os:
            parts.append(str(self.host_os))
        elif self.host_architecture:
            parts.append(str(self.host_architecture))
        if self.prefix_id:
            parts.append(f"prefix:{self.prefix_id[:12]}")
        return " | ".join(parts) if parts else "environment observed"


def _prefix_id_from_env(env: Mapping[str, str]) -> Optional[str]:
    prefix = str(env.get("WINEPREFIX") or "").strip()
    if not prefix:
        return None
    return sha256_v1({"prefix_path": prefix})


def _host_os_from_hardware(hardware_profile: Mapping[str, Any]) -> Optional[str]:
    os_name = str(hardware_profile.get("os") or "").strip()
    if not os_name:
        return None
    distribution = hardware_profile.get("distribution")
    if distribution:
        return f"{os_name} ({distribution})"
    return os_name


def _kernel_version_from_hardware(hardware_profile: Mapping[str, Any]) -> Optional[str]:
    kernel = str(hardware_profile.get("os_version") or "").strip()
    if kernel:
        return kernel
    try:
        release = platform.release()
        return release if release else None
    except Exception:  # noqa: BLE001
        return None


def _runtime_identities(
    *,
    record: AttemptRecord,
    hardware_profile: Mapping[str, Any],
) -> List[str]:
    identities: List[str] = []
    runtime = str(record.runtime or "").strip().lower()
    if runtime:
        identities.append(f"runtime:{runtime}")
    phase = str(record.phase or "").strip().lower()
    if phase:
        identities.append(f"phase:{phase}")
    paths = hardware_profile.get("paths") or {}
    if isinstance(paths, dict):
        wine_path = paths.get("wine")
        if wine_path:
            identities.append(f"wine_binary:{wine_path}")
        proton_path = paths.get("proton")
        if proton_path:
            identities.append(f"proton_binary:{proton_path}")
    return sorted_list(identities)


def capture_run_environment(
    *,
    hardware_profile: Mapping[str, Any],
    record: AttemptRecord,
    wine_version: Optional[str] = None,
) -> Optional[CompatibilityRunEnvironment]:
    """Build a run environment snapshot from available session data only."""
    env = record.env or {}
    prefix = str(env.get("WINEPREFIX") or "").strip()
    wine_architecture: Optional[str] = None
    if prefix:
        try:
            wine_architecture = _detect_prefix_architecture(prefix)
        except Exception:  # noqa: BLE001
            wine_architecture = None

    host_arch = hardware_profile.get("architecture")
    runtime_identities = _runtime_identities(record=record, hardware_profile=hardware_profile)

    snapshot = CompatibilityRunEnvironment(
        alma_bridge_version=alma_bridge_version,
        host_os=_host_os_from_hardware(hardware_profile),
        kernel_version=_kernel_version_from_hardware(hardware_profile),
        host_architecture=str(host_arch).strip() if host_arch else None,
        wine_version=str(wine_version).strip() if wine_version else None,
        wine_architecture=wine_architecture,
        prefix_id=_prefix_id_from_env(env),
        prefix_schema_version=MANIFEST_CAPTURE_VERSION if prefix else None,
        relevant_runtime_identities=runtime_identities,
        execution_strategy_version=str(record.phase or record.strategy_id or "").strip() or None,
    )

    canonical = snapshot.to_canonical_dict()
    if len(canonical) <= 1:
        return None
    return snapshot


def environment_from_dict(payload: Mapping[str, Any]) -> Optional[CompatibilityRunEnvironment]:
    if not payload:
        return None
    try:
        return CompatibilityRunEnvironment.model_validate(dict(payload))
    except Exception:  # noqa: BLE001
        return None


def environment_to_dict(environment: CompatibilityRunEnvironment) -> Dict[str, Any]:
    return environment.to_canonical_dict()
