from __future__ import annotations

import json
from pathlib import Path

import pytest

from alma_bridge.compatibility.expected_verification_contract import (
    ExpectedVerificationContract,
    expected_verification_contract_for_kind,
)
from alma_bridge.compatibility.profile_fingerprints import (
    build_verification_binding_key,
    build_verification_binding_payload,
)
from alma_bridge.compatibility.profile_lineage import promote_candidate_snapshot
from alma_bridge.compatibility.profile_shadow_eligibility import evaluate_candidate_eligibility
from alma_bridge.compatibility.profile_shadow_reasons import EligibilityReasonCode
from alma_bridge.compatibility.profile_store import load_profile_bundle
from alma_bridge.compatibility.verification_binding_compatibility import (
    evaluate_verification_binding_compatibility,
)
from alma_bridge.session.services.verification import (
    DEFAULT_POLICY_ID,
    DEFAULT_POLICY_VERSION,
    WINE_GUI_POLICY_ID,
    WINE_GUI_POLICY_VERSION,
)
from alma_bridge.storage import outcomes
from tests.pe_test_helpers import write_minimal_pe
from alma_bridge.compatibility.program_kind import IMAGE_SUBSYSTEM_WINDOWS_GUI
from tests.profile_test_helpers import (
    build_test_snapshot,
    sample_verification_payload,
    sample_wine_gui_verification_payload,
)


@pytest.fixture
def pe_gui_exe(tmp_path):
    path = tmp_path / "notepad.exe"
    write_minimal_pe(path, subsystem=IMAGE_SUBSYSTEM_WINDOWS_GUI)
    return path


@pytest.fixture
def profile_env(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profiles_enabled", True)
    outcomes.init_outcome_store()
    return db


def _wine_gui_bundle(
    *,
    pe_gui_exe: Path,
    executable_hash: str = "108168df2b9679c5ef4004a5fa63990c99b189661ee3cac4bb8f9dd467ad6d69",
    session_id: str = "wine-gui-sess",
):
    snap = build_test_snapshot(
        session_id=session_id,
        file_path=str(pe_gui_exe),
        executable_hash=executable_hash,
        strategy_id="wine_host",
        runtime="wine",
        phase="wine_gui",
        verification_payload=sample_wine_gui_verification_payload(),
    )
    profile_id, _ = promote_candidate_snapshot(snap)
    bundle = load_profile_bundle(profile_id)
    assert bundle is not None
    return profile_id, bundle


def test_pilot002_scenario_id_mismatch_caught_before_freeze():
    repo = Path(__file__).resolve().parents[1]
    scenario_manifest = json.loads(
        (repo / "data/validation/shadow_scenario_manifest_v1.json").read_text(encoding="utf-8")
    )
    manifest_ids = {s["scenario_id"] for s in scenario_manifest["scenarios"]}
    pilot002_matrix = [
        {"run_number": 6, "scenario_id": "E_prefix_drift", "scenario_category": "E_prefix_drift",
         "target_id": "T2", "program_kind": "pe_windows_gui", "application_family": "wine_builtin_notepad64",
         "disposable_env": "runs/run-06"},
    ]
    from alma_bridge.validation.campaign_freeze_validator import (
        validate_campaign_matrix,
        validate_pilot002_mismatch_would_fail,
    )

    assert validate_pilot002_mismatch_would_fail(pilot002_matrix, manifest_ids)
    result = validate_campaign_matrix(
        campaign_manifest={"campaign_id": "shadow-validation-pilot-002", "feature_flags": {}},
        matrix_runs=pilot002_matrix,
        scenario_manifest_path=repo / "data/validation/shadow_scenario_manifest_v1.json",
        repo_root=repo,
    )
    assert result.passed is False
    assert any(i.code == "SCENARIO_ID_MANIFEST_MISMATCH" for i in result.issues)


def test_pilot003_matrix_passes_scenario_id_validation():
    repo = Path(__file__).resolve().parents[1]
    matrix_doc = json.loads(
        (repo / "data/validation/campaigns/pilot-003-matrix.json").read_text(encoding="utf-8")
    )
    campaign_manifest = json.loads(
        (repo / "data/validation/campaigns/shadow-validation-pilot-003.json").read_text(encoding="utf-8")
    )
    from alma_bridge.validation.campaign_freeze_validator import validate_campaign_matrix

    result = validate_campaign_matrix(
        campaign_manifest=campaign_manifest,
        matrix_runs=matrix_doc["runs"],
        scenario_manifest_path=repo / "data/validation/shadow_scenario_manifest_v1.json",
        repo_root=repo,
        evidence_dir=repo / "data" / "validation" / "evidence" / "pilot-003",
    )
    assert not any(i.code == "SCENARIO_ID_MANIFEST_MISMATCH" for i in result.issues)
    # Pilot-003 is aborted; semantic validator must catch known corrective defects.
    semantic_codes = {i.code for i in result.issues}
    assert "PRE_PLAN_OVERLAY_REQUIRED" in semantic_codes or "POST_HOC_OVERLAY_FORBIDDEN" in semantic_codes


def test_wine_gui_profile_exact_policy_compatible(profile_env, pe_gui_exe):
    _, bundle = _wine_gui_bundle(pe_gui_exe=pe_gui_exe)
    expected = expected_verification_contract_for_kind({"program_kind": "pe_windows_gui"})
    result = evaluate_verification_binding_compatibility(
        profile_bundle=bundle,
        expected=expected,
    )
    assert result.compatible is True
    assert result.reason_codes == []


def test_wine_gui_profile_eligible_for_matching_run(profile_env, pe_gui_exe):
    _, bundle = _wine_gui_bundle(pe_gui_exe=pe_gui_exe)
    expected = expected_verification_contract_for_kind({"program_kind": "pe_windows_gui"})
    evaluation = evaluate_candidate_eligibility(
        profile_bundle=bundle,
        program_identity_key=bundle["program"]["program_identity_key"],
        host_compatibility_class_id=bundle["profile"]["host_compatibility_class_id"],
        host_payload=json.loads(bundle["host"]["host_class_json"]),
        expected_verification=expected,
    )
    assert evaluation.eligibility_status == "eligible"
    assert EligibilityReasonCode.VERIFICATION_BINDING_INCOMPATIBLE.value not in evaluation.rejection_reason_codes


def test_t2_t3_do_not_cross_match(profile_env, pe_gui_exe):
    t2_id, t2_bundle = _wine_gui_bundle(
        pe_gui_exe=pe_gui_exe,
        executable_hash="108168df2b9679c5ef4004a5fa63990c99b189661ee3cac4bb8f9dd467ad6d69",
        session_id="t2-sess",
    )
    t3_id, t3_bundle = _wine_gui_bundle(
        pe_gui_exe=pe_gui_exe,
        executable_hash="a2bddbb8d43eb96b750813ab8f30db847d2b60d2838dd5fcb36348a719157266",
        session_id="t3-sess",
    )
    expected = expected_verification_contract_for_kind({"program_kind": "pe_windows_gui"})
    t2_on_t3 = evaluate_candidate_eligibility(
        profile_bundle=t2_bundle,
        program_identity_key=t3_bundle["program"]["program_identity_key"],
        host_compatibility_class_id=t2_bundle["profile"]["host_compatibility_class_id"],
        host_payload=json.loads(t2_bundle["host"]["host_class_json"]),
        expected_verification=expected,
    )
    assert EligibilityReasonCode.PROGRAM_IDENTITY_MISMATCH.value in t2_on_t3.rejection_reason_codes


def test_native_profile_rejects_wine_gui_policy(profile_env):
    snap = build_test_snapshot(verification_payload=sample_verification_payload())
    profile_id, _ = promote_candidate_snapshot(snap)
    bundle = load_profile_bundle(profile_id)
    expected = expected_verification_contract_for_kind({"program_kind": "pe_windows_gui"})
    evaluation = evaluate_candidate_eligibility(
        profile_bundle=bundle,
        program_identity_key=bundle["program"]["program_identity_key"],
        host_compatibility_class_id=bundle["profile"]["host_compatibility_class_id"],
        host_payload=json.loads(bundle["host"]["host_class_json"]),
        expected_verification=expected,
    )
    assert EligibilityReasonCode.VERIFICATION_POLICY_ID_MISMATCH.value in evaluation.rejection_reason_codes


def test_policy_version_incompatible_rejected(profile_env, pe_gui_exe):
    _, bundle = _wine_gui_bundle(pe_gui_exe=pe_gui_exe)
    expected = ExpectedVerificationContract(
        policy_id=WINE_GUI_POLICY_ID,
        policy_version="9.9.9",
        phase="wine_gui",
        program_kind="pe_windows_gui",
        required_checks=["process_survives"],
        optional_checks=[],
    )
    result = evaluate_verification_binding_compatibility(profile_bundle=bundle, expected=expected)
    assert EligibilityReasonCode.VERIFICATION_POLICY_VERSION_INCOMPATIBLE.value in result.reason_codes


def test_required_checks_removed_incompatible(profile_env, pe_gui_exe):
    _, bundle = _wine_gui_bundle(pe_gui_exe=pe_gui_exe)
    expected = ExpectedVerificationContract(
        policy_id=WINE_GUI_POLICY_ID,
        policy_version=WINE_GUI_POLICY_VERSION,
        phase="wine_gui",
        program_kind="pe_windows_gui",
        required_checks=["process_survives", "target_process_identity", "extra_check"],
        optional_checks=[],
    )
    result = evaluate_verification_binding_compatibility(profile_bundle=bundle, expected=expected)
    assert EligibilityReasonCode.REQUIRED_CHECKS_MISMATCH.value in result.reason_codes


def test_unknown_policy_rejected(profile_env, pe_gui_exe):
    _, bundle = _wine_gui_bundle(pe_gui_exe=pe_gui_exe)
    verification = dict(bundle.get("verification") or {})
    verification["policy_id"] = "unknown_policy_v99"
    bundle = dict(bundle)
    bundle["verification"] = verification
    expected = expected_verification_contract_for_kind({"program_kind": "pe_windows_gui"})
    result = evaluate_verification_binding_compatibility(profile_bundle=bundle, expected=expected)
    assert EligibilityReasonCode.VERIFICATION_POLICY_UNKNOWN.value in result.reason_codes


def test_detailed_reason_codes_persisted_in_eligibility(profile_env, pe_gui_exe):
    _, bundle = _wine_gui_bundle(pe_gui_exe=pe_gui_exe)
    expected = ExpectedVerificationContract(
        policy_id=DEFAULT_POLICY_ID,
        policy_version=DEFAULT_POLICY_VERSION,
        phase="native",
        program_kind="pe_windows_gui",
        required_checks=["exit_code_zero"],
        optional_checks=[],
    )
    evaluation = evaluate_candidate_eligibility(
        profile_bundle=bundle,
        program_identity_key=bundle["program"]["program_identity_key"],
        host_compatibility_class_id=bundle["profile"]["host_compatibility_class_id"],
        host_payload=json.loads(bundle["host"]["host_class_json"]),
        expected_verification=expected,
    )
    assert EligibilityReasonCode.VERIFICATION_POLICY_ID_MISMATCH.value in evaluation.rejection_reason_codes
    assert EligibilityReasonCode.VERIFICATION_BINDING_INCOMPATIBLE.value in evaluation.rejection_reason_codes


def test_verifier_binding_key_mismatch_rejected(profile_env, pe_gui_exe):
    _, bundle = _wine_gui_bundle(pe_gui_exe=pe_gui_exe)
    profile = dict(bundle["profile"])
    profile["verification_binding_key"] = "deadbeef"
    bundle = dict(bundle)
    bundle["profile"] = profile
    expected = expected_verification_contract_for_kind({"program_kind": "pe_windows_gui"})
    result = evaluate_verification_binding_compatibility(profile_bundle=bundle, expected=expected)
    assert EligibilityReasonCode.VERIFIER_VERSION_INCOMPATIBLE.value in result.reason_codes
