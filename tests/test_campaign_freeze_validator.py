from __future__ import annotations

import json
from pathlib import Path

import pytest

from alma_bridge.validation.campaign_freeze_validator import validate_campaign_matrix


REPO = Path(__file__).resolve().parents[1]
SCENARIO_MANIFEST = REPO / "data" / "validation" / "shadow_scenario_manifest_v1.json"


def _base_campaign(**overrides):
    base = {
        "campaign_id": "shadow-validation-pilot-003",
        "feature_flags": {
            "ALMA_BRIDGE_COMPATIBILITY_PROFILE_REUSE_ENABLED": False,
            "ALMA_BRIDGE_VALIDATION_CAMPAIGN_MODE": True,
        },
        "legacy_profile_exclusion": {
            "excluded_profile_ids": [
                "425f8664-7ddd-4a99-b984-435051027e8f",
                "bebf5c5f-6719-4ac2-8e75-29ac6c839bf3",
            ]
        },
        "target_paths": {"ascension_primary_prefix": "guard_reference_only_not_execution_target"},
        "target_programs": [
            {
                "target_id": "T1_native_success_probe",
                "canonical_path": "scripts/validation/native_success_probe.sh",
            }
        ],
    }
    base.update(overrides)
    return base


def test_duplicate_run_number_fails():
    runs = [
        {"run_number": 1, "scenario_id": "A_stable_repeat_success", "target_id": "T1",
         "program_kind": "native_script", "application_family": "alma_validation_native",
         "disposable_env": "r1"},
        {"run_number": 1, "scenario_id": "B_relocated_executable", "target_id": "T1",
         "program_kind": "native_script", "application_family": "alma_validation_native",
         "disposable_env": "r2"},
    ]
    result = validate_campaign_matrix(
        campaign_manifest=_base_campaign(),
        matrix_runs=runs,
        scenario_manifest_path=SCENARIO_MANIFEST,
        repo_root=REPO,
    )
    assert result.passed is False
    assert any(i.code == "DUPLICATE_RUN_NUMBER" for i in result.issues)


def test_active_reuse_enabled_fails():
    matrix = json.loads(
        (REPO / "data/validation/campaigns/pilot-003-matrix.json").read_text(encoding="utf-8")
    )
    result = validate_campaign_matrix(
        campaign_manifest=_base_campaign(
            feature_flags={
                "ALMA_BRIDGE_COMPATIBILITY_PROFILE_REUSE_ENABLED": True,
                "ALMA_BRIDGE_VALIDATION_CAMPAIGN_MODE": True,
            }
        ),
        matrix_runs=matrix["runs"],
        scenario_manifest_path=SCENARIO_MANIFEST,
        repo_root=REPO,
    )
    assert result.passed is False
    assert any(i.code == "ACTIVE_REUSE_ENABLED" for i in result.issues)


def test_missing_scenario_metadata_fails():
    runs = [
        {"run_number": 1, "scenario_id": "A_stable_repeat_success", "target_id": "",
         "program_kind": "", "application_family": "", "disposable_env": ""},
    ]
    result = validate_campaign_matrix(
        campaign_manifest=_base_campaign(),
        matrix_runs=runs,
        scenario_manifest_path=SCENARIO_MANIFEST,
        repo_root=REPO,
    )
    assert result.passed is False
    assert any(i.code == "MISSING_SCENARIO_METADATA" for i in result.issues)


def test_pilot002_e_prefix_drift_would_fail_freeze():
    runs = [
        {"run_number": 6, "scenario_id": "E_prefix_drift", "scenario_category": "E_prefix_drift",
         "target_id": "T2_wine_notepad64", "program_kind": "pe_windows_gui",
         "application_family": "wine_builtin_notepad64", "disposable_env": "run-06"},
    ]
    result = validate_campaign_matrix(
        campaign_manifest=_base_campaign(campaign_id="shadow-validation-pilot-002"),
        matrix_runs=runs,
        scenario_manifest_path=SCENARIO_MANIFEST,
        repo_root=REPO,
    )
    assert result.passed is False
    codes = {i.code for i in result.issues}
    assert "SCENARIO_ID_MANIFEST_MISMATCH" in codes
