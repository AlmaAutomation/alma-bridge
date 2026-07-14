from __future__ import annotations

import json
from pathlib import Path

import pytest

from alma_bridge.compatibility.profile_shadow_comparison import build_shadow_comparison_metrics
from alma_bridge.compatibility.profile_shadow_validation_labels import (
    TrustCategory,
    ValidationLabelType,
    expected_imported_trust_label,
    is_trust_category_value,
    parse_validation_label_type,
)
from alma_bridge.compatibility.profile_shadow_validation_store import add_label
from alma_bridge.compatibility.profile_shadow_validation_models import ShadowLabelInput
from alma_bridge.validation.campaign_semantic_validator import validate_campaign_semantics
from alma_bridge.validation.prefix_drift import (
    COMPONENT_MARKERS,
    read_prefix_installed_components,
    remove_component_from_prefix,
)
from alma_bridge.validation.campaign_freeze_validator import validate_campaign_matrix

REPO = Path(__file__).resolve().parents[1]
SCENARIO_MANIFEST = REPO / "data" / "validation" / "shadow_scenario_manifest_v1.json"


def test_trust_category_is_not_valid_label():
    with pytest.raises(ValueError, match="trust category"):
        parse_validation_label_type(TrustCategory.SHADOW_OBSERVATION_ONLY.value)


def test_imported_trust_expected_label():
    assert expected_imported_trust_label() == ValidationLabelType.REJECTED_CORRECT


def test_add_label_rejects_trust_category_as_label(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    from alma_bridge.storage import outcomes
    from alma_bridge.compatibility.profile_shadow_store import init_shadow_store, persist_shadow_prediction
    from alma_bridge.compatibility.profile_shadow_validation_store import init_validation_store

    outcomes.init_outcome_store()
    init_shadow_store()
    init_validation_store()
    shadow_event_id = "00000000-0000-0000-0000-000000000099"
    persist_shadow_prediction(
        shadow_event_id=shadow_event_id,
        session_id="sess-label-test",
        correlation_id="sess-label-test",
        program_identity_key="pk",
        executable_hash="eh",
        host_compatibility_class_id="hk",
        ranking_formula_id="r",
        ranking_formula_version="1",
        ranking_status="completed",
        selected_profile_id=None,
        selected_profile_revision=None,
        predicted_strategy_id=None,
        predicted_bridge_family_key=None,
        predicted_remediation_protocol=[],
        feature_flags={},
        model_version=None,
        candidates=[],
    )
    with pytest.raises(ValueError, match="trust category"):
        add_label(
            ShadowLabelInput(
                shadow_event_id=shadow_event_id,
                label_type="shadow_observation_only",
                label_source="operator",
                reviewer="test",
                reason="invalid",
            )
        )


def test_pilot003_matrix_label_defect_caught():
    matrix = json.loads((REPO / "data/validation/campaigns/pilot-003-matrix.json").read_text())
    # Inject Pilot-003 defect into synthetic run for validator
    runs = list(matrix["runs"])
    runs.append(
        {
            "run_number": 99,
            "scenario_id": "I_trust_state_imported",
            "expected_labels": ["shadow_observation_only"],
        }
    )
    result = validate_campaign_semantics(
        campaign_manifest={"campaign_id": "test", "feature_flags": {"ALMA_BRIDGE_COMPATIBILITY_PROFILE_REUSE_ENABLED": False}},
        matrix_runs=runs,
        repo_root=REPO,
    )
    assert any(i.code == "PILOT003_DEFECT_LABEL" for i in result.issues)


def test_pilot004_matrix_host_overlay_requires_pre_plan():
    matrix = json.loads((REPO / "data/validation/campaigns/pilot-004-matrix.json").read_text())
    campaign = json.loads((REPO / "data/validation/campaigns/shadow-validation-pilot-004.json").read_text())
    result = validate_campaign_semantics(
        campaign_manifest=campaign,
        matrix_runs=matrix["runs"],
        repo_root=REPO,
    )
    assert not any(i.code == "PRE_PLAN_OVERLAY_REQUIRED" for i in result.issues)
    run4 = next(r for r in result.resolved_plan if r.run_number == 4)
    assert run4.host_overlay == {"host_arch": "aarch64"}


def test_pilot004_commands_reject_invalid_label():
    commands = (REPO / "data/validation/campaigns/pilot-004-commands.md").read_text()
    assert "shadow_observation_only" not in commands or "NOT" in commands
    assert "rejected_correct" in commands


def test_duplicate_lineage_only_when_promoted_differs():
    metrics = build_shadow_comparison_metrics(
        prediction={"selected_profile_id": "profile-a", "predicted_strategy_id": "wine_host"},
        candidates=[
            {
                "profile_id": "profile-a",
                "eligibility_status": "eligible",
                "bridge_family_match_dimensions_json": "{}",
            }
        ],
        actual={"actual_success": True, "actual_strategy_id": "wine_host"},
        profile_candidate_id="cand-1",
    )
    assert metrics["duplicate_predicted_lineage"] == 0


def test_component_marker_removal(tmp_path):
    prefix = tmp_path / "prefix"
    for marker in COMPONENT_MARKERS["corefonts"]:
        path = prefix / marker
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    assert "corefonts" in read_prefix_installed_components(str(prefix))
    ok, _ = remove_component_from_prefix(str(prefix), "corefonts")
    assert ok
    assert "corefonts" not in read_prefix_installed_components(str(prefix))


def test_pilot003_post_hoc_overlay_flagged_in_semantic_validator():
    runs = [
        {
            "run_number": 4,
            "scenario_id": "D_incompatible_host_drift",
            "shadow_scenario_inputs": {
                "host_payload_overlay": {"host_arch": "aarch64"},
                "evaluation_mode": "shadow_read_only_host_class_mismatch",
            },
        }
    ]
    result = validate_campaign_semantics(
        campaign_manifest={"campaign_id": "pilot-003-repro"},
        matrix_runs=runs,
        repo_root=REPO,
    )
    assert any(i.code == "POST_HOC_OVERLAY_FORBIDDEN" for i in result.issues)
