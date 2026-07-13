from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from alma_bridge.compatibility.profile_fingerprints import BRIDGE_MANIFEST_SCHEMA
from alma_bridge.compatibility.profile_shadow_models import DriftDimension
from alma_bridge.compatibility.profile_shadow_reasons import EligibilityReasonCode
from alma_bridge.execution.installer_verify import snapshot_wine_prefix
from alma_bridge.execution.preflight import read_wine_windows_version


def predict_bridge_drift(
    *,
    profile_manifest: Mapping[str, Any],
    wine_prefix: Optional[str],
    launcher_file_hash: Optional[str] = None,
) -> tuple[List[DriftDimension], str]:
    """
    Read-only drift prediction. Never mutates prefix or bridge state.
    Returns drift dimensions and aggregate result label.
    """
    dimensions: List[DriftDimension] = []
    prefix_path = Path(wine_prefix).expanduser() if wine_prefix else None
    prefix_exists = bool(prefix_path and prefix_path.exists())

    expected_windows = profile_manifest.get("windows_version")
    observed_windows = None
    if prefix_exists:
        try:
            observed_windows = read_wine_windows_version(str(prefix_path))
        except Exception:  # noqa: BLE001
            observed_windows = None
    if expected_windows:
        if not prefix_exists:
            dimensions.append(
                DriftDimension(
                    dimension="windows_version",
                    status="indeterminate",
                    reason_code="PREFIX_UNAVAILABLE",
                    expected=expected_windows,
                    observed=None,
                    severity=0.25,
                )
            )
        elif observed_windows != expected_windows:
            dimensions.append(
                DriftDimension(
                    dimension="windows_version",
                    status="drift",
                    reason_code="WINDOWS_VERSION_DRIFT",
                    expected=expected_windows,
                    observed=observed_windows,
                    severity=0.6,
                )
            )
        else:
            dimensions.append(
                DriftDimension(
                    dimension="windows_version",
                    status="match",
                    reason_code="WINDOWS_VERSION_MATCH",
                    expected=expected_windows,
                    observed=observed_windows,
                    severity=0.0,
                )
            )

    expected_components = list(profile_manifest.get("installed_components") or [])
    if expected_components:
        if not prefix_exists:
            dimensions.append(
                DriftDimension(
                    dimension="installed_components",
                    status="indeterminate",
                    reason_code="PREFIX_UNAVAILABLE",
                    expected=expected_components,
                    observed=None,
                    severity=0.2,
                )
            )
        else:
            dimensions.append(
                DriftDimension(
                    dimension="installed_components",
                    status="indeterminate",
                    reason_code="COMPONENT_INSPECTION_READONLY_LIMITED",
                    expected=expected_components,
                    observed="not_mutated_readonly",
                    severity=0.15,
                )
            )

    expected_dll = profile_manifest.get("dll_overrides") or {}
    if expected_dll:
        dimensions.append(
            DriftDimension(
                dimension="dll_overrides",
                status="indeterminate",
                reason_code="DLL_OVERRIDE_READONLY_LIMITED",
                expected=expected_dll,
                observed=None,
                severity=0.1,
            )
        )

    expected_hashes = profile_manifest.get("config_file_hashes") or {}
    if expected_hashes and prefix_exists:
        try:
            snap = snapshot_wine_prefix(str(prefix_path), max_files=2000)
            observed_hashes = {
                name: snap.file_hashes.get(name)
                for name in expected_hashes
                if name in snap.file_hashes
            }
            mismatched = [
                name
                for name, expected in expected_hashes.items()
                if observed_hashes.get(name) and observed_hashes.get(name) != expected
            ]
            if mismatched:
                dimensions.append(
                    DriftDimension(
                        dimension="config_file_hashes",
                        status="drift",
                        reason_code="CONFIG_HASH_DRIFT",
                        expected=expected_hashes,
                        observed=observed_hashes,
                        severity=0.5,
                    )
                )
            else:
                dimensions.append(
                    DriftDimension(
                        dimension="config_file_hashes",
                        status="match",
                        reason_code="CONFIG_HASH_MATCH",
                        expected=expected_hashes,
                        observed=observed_hashes,
                        severity=0.0,
                    )
                )
        except Exception:  # noqa: BLE001
            dimensions.append(
                DriftDimension(
                    dimension="config_file_hashes",
                    status="indeterminate",
                    reason_code="CONFIG_HASH_INSPECTION_FAILED",
                    expected=expected_hashes,
                    observed=None,
                    severity=0.2,
                )
            )
    elif expected_hashes:
        dimensions.append(
            DriftDimension(
                dimension="config_file_hashes",
                status="indeterminate",
                reason_code="PREFIX_UNAVAILABLE",
                expected=expected_hashes,
                observed=None,
                severity=0.2,
            )
        )

    expected_wrappers = profile_manifest.get("wrapper_versions") or {}
    if expected_wrappers:
        dimensions.append(
            DriftDimension(
                dimension="wrapper_versions",
                status="indeterminate",
                reason_code="WRAPPER_VERSION_READONLY_LIMITED",
                expected=expected_wrappers,
                observed=None,
                severity=0.1,
            )
        )

    expected_launcher_hash = profile_manifest.get("launcher_file_hash")
    if expected_launcher_hash:
        if launcher_file_hash and launcher_file_hash != expected_launcher_hash:
            dimensions.append(
                DriftDimension(
                    dimension="launcher_file_hash",
                    status="drift",
                    reason_code="LAUNCHER_HASH_DRIFT",
                    expected=expected_launcher_hash,
                    observed=launcher_file_hash,
                    severity=0.4,
                )
            )
        elif not launcher_file_hash:
            dimensions.append(
                DriftDimension(
                    dimension="launcher_file_hash",
                    status="indeterminate",
                    reason_code="LAUNCHER_HASH_UNAVAILABLE",
                    expected=expected_launcher_hash,
                    observed=None,
                    severity=0.15,
                )
            )
        else:
            dimensions.append(
                DriftDimension(
                    dimension="launcher_file_hash",
                    status="match",
                    reason_code="LAUNCHER_HASH_MATCH",
                    expected=expected_launcher_hash,
                    observed=launcher_file_hash,
                    severity=0.0,
                )
            )

    schema = str(profile_manifest.get("schema") or "")
    if schema and schema != BRIDGE_MANIFEST_SCHEMA:
        dimensions.append(
            DriftDimension(
                dimension="manifest_schema",
                status="drift",
                reason_code=EligibilityReasonCode.MANIFEST_SCHEMA_UNSUPPORTED.value,
                expected=BRIDGE_MANIFEST_SCHEMA,
                observed=schema,
                severity=1.0,
            )
        )

    if not dimensions:
        return [], "no_manifest_signals"

    drift_count = sum(1 for d in dimensions if d.status == "drift")
    indeterminate_count = sum(1 for d in dimensions if d.status == "indeterminate")
    if drift_count:
        return dimensions, "drift_detected"
    if indeterminate_count == len(dimensions):
        return dimensions, "indeterminate"
    return dimensions, "no_drift_detected"
