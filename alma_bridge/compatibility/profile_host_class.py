from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional

from alma_bridge.compatibility.profile_fingerprints import sha256_v1, sorted_list

HOST_CLASS_SCHEMA = "host_class_v1"


def _wine_major(wine_version: Optional[str]) -> Optional[str]:
    if not wine_version:
        return None
    match = re.search(r"(\d+)\.", wine_version)
    return match.group(1) if match else wine_version.split(".", 1)[0]


def _os_family(os_id: Optional[str], os_like: Optional[str] = None) -> str:
    if os_id:
        return str(os_id).lower()
    if os_like:
        return str(os_like).split()[0].lower()
    return "unknown"


def _gpu_class(hardware: Mapping[str, Any], *, program_needs_gpu: bool) -> Optional[str]:
    if not program_needs_gpu:
        return None
    gpu = hardware.get("gpu") or {}
    vendor = str(gpu.get("vendor") or "unknown").lower()
    driver = str(gpu.get("driver") or "unknown").lower()
    driver_major = driver.split(".", 1)[0] if driver else "unknown"
    return f"{vendor}:{driver_major}"


def build_host_compatibility_class_payload(
    hardware: Mapping[str, Any],
    *,
    wine_version: Optional[str] = None,
    proton_family: Optional[str] = None,
    program_needs_gpu: bool = False,
) -> Dict[str, Any]:
    capabilities = hardware.get("capabilities") or {}
    capability_set = sorted_list(
        [name for name, enabled in capabilities.items() if enabled]
    )
    distribution = hardware.get("distribution") or {}
    os_id = distribution.get("id") if isinstance(distribution, dict) else None
    os_like = distribution.get("id_like") if isinstance(distribution, dict) else None
    return {
        "schema": HOST_CLASS_SCHEMA,
        "os_family": _os_family(os_id, os_like),
        "host_arch": str(hardware.get("architecture") or "unknown"),
        "wine_major": _wine_major(wine_version),
        "proton_family": proton_family,
        "capability_set": capability_set,
        "gpu_class": _gpu_class(hardware, program_needs_gpu=program_needs_gpu),
    }


def build_host_compatibility_class_id(payload: Mapping[str, Any]) -> str:
    return sha256_v1(payload)
