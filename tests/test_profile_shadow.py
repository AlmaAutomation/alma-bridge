from __future__ import annotations

import ast
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from alma_bridge.compatibility.profile_lineage import promote_candidate_snapshot
from alma_bridge.compatibility.profile_metrics import get_profile_counters, reset_profile_counters
from alma_bridge.compatibility.profile_shadow import ProfileShadowService, shadow_mode_enabled
from alma_bridge.compatibility.profile_shadow_drift import predict_bridge_drift
from alma_bridge.compatibility.profile_shadow_eligibility import evaluate_candidate_eligibility
from alma_bridge.compatibility.profile_shadow_models import ShadowActualInputs, ShadowPlanningInputs
from alma_bridge.compatibility.profile_shadow_ranking import rank_eligible_candidates, select_predicted_winner
from alma_bridge.compatibility.profile_shadow_reasons import EligibilityReasonCode
from alma_bridge.compatibility.profile_shadow_store import (
    ensure_shadow_tables,
    load_shadow_candidates,
    load_shadow_prediction,
)
from alma_bridge.compatibility.profile_store import (
    _connect,
    ensure_profile_tables,
    insert_invalidation,
    load_profile_bundle,
)
from alma_bridge.learning.orchestrator import BridgeOrchestrator
from alma_bridge.schemas.models import AttemptRecord, BridgeRequest, BridgeSessionResult, ExecutionMode
from alma_bridge.session.lifecycle import SessionLifecycleManager
from alma_bridge.session.state import SessionState
from alma_bridge.storage import outcomes
from tests.profile_test_helpers import build_test_snapshot, sample_hardware, sample_verification_payload

ROOT = Path(__file__).resolve().parents[1]
SHADOW_DIR = ROOT / "alma_bridge" / "compatibility"


@pytest.fixture
def shadow_env(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profiles_enabled", True)
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profile_shadow_mode", True)
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profile_creation_enabled", True)
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profile_reuse_enabled", False)
    outcomes.init_outcome_store()
    reset_profile_counters()
    return db


def _seed_verified_profile(session_id: str = "seed-sess") -> str:
    snap = build_test_snapshot(session_id=session_id)
    profile_id, _ = promote_candidate_snapshot(snap)
    return profile_id


def _bundle(profile_id: str):
    bundle = load_profile_bundle(profile_id)
    assert bundle is not None
    return bundle


def test_shadow_mode_requires_both_flags(monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profiles_enabled", False)
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profile_shadow_mode", True)
    assert shadow_mode_enabled() is False


def test_prediction_persisted_before_planner_invocation(shadow_env):
    profile_id = _seed_verified_profile()
    snap = build_test_snapshot()
    inputs = ShadowPlanningInputs(
        session_id="shadow-sess-1",
        correlation_id="corr-1",
        file_path="/tmp/game.sh",
        executable_hash=snap.program_identity_payload["executable_hash"],
        hardware=sample_hardware(),
    )
    event_id = ProfileShadowService.create_prediction(inputs)
    assert event_id
    prediction = load_shadow_prediction("shadow-sess-1")
    assert prediction is not None
    assert prediction["selected_profile_id"] == profile_id
    candidates = load_shadow_candidates(event_id)
    assert len(candidates) == 1
    assert candidates[0]["eligibility_status"] == "eligible"


def test_prediction_immutable_after_execution(shadow_env):
    snap = build_test_snapshot()
    inputs = ShadowPlanningInputs(
        session_id="immutable-sess",
        correlation_id="corr-imm",
        file_path="/tmp/game.sh",
        executable_hash=snap.program_identity_payload["executable_hash"],
        hardware=sample_hardware(),
    )
    _seed_verified_profile("other-sess")
    event_id = ProfileShadowService.create_prediction(inputs)
    original = load_shadow_prediction("immutable-sess")
    ProfileShadowService.record_actual_outcome(
        ShadowActualInputs(
            session_id="immutable-sess",
            correlation_id="corr-imm",
            terminal_session_state="SUCCEEDED",
            success=True,
            actual_strategy_id="native_direct",
        )
    )
    after = load_shadow_prediction("immutable-sess")
    assert original == after
    assert original["shadow_event_id"] == event_id


def test_actual_outcome_stored_separately(shadow_env):
    snap = build_test_snapshot()
    _seed_verified_profile()
    inputs = ShadowPlanningInputs(
        session_id="actual-sess",
        correlation_id="corr-act",
        file_path="/tmp/game.sh",
        executable_hash=snap.program_identity_payload["executable_hash"],
        hardware=sample_hardware(),
    )
    ProfileShadowService.create_prediction(inputs)
    actual_id = ProfileShadowService.record_actual_outcome(
        ShadowActualInputs(
            session_id="actual-sess",
            correlation_id="corr-act",
            terminal_session_state="FAILED",
            success=False,
            failure_signature="execution_failed",
        )
    )
    assert actual_id
    with _connect() as conn:
        ensure_profile_tables(conn)
        ensure_shadow_tables(conn)
        row = conn.execute(
            "SELECT * FROM compatibility_profile_shadow_actual_outcomes WHERE session_id = ?",
            ("actual-sess",),
        ).fetchone()
        comparison = conn.execute(
            "SELECT * FROM compatibility_profile_shadow_comparisons WHERE session_id = ?",
            ("actual-sess",),
        ).fetchone()
    assert row is not None
    assert comparison is not None


def test_program_identity_mismatch_rejection(shadow_env):
    profile_id = _seed_verified_profile()
    bundle = _bundle(profile_id)
    evaluation = evaluate_candidate_eligibility(
        profile_bundle=bundle,
        program_identity_key="different-key",
        host_compatibility_class_id=bundle["profile"]["host_compatibility_class_id"],
        host_payload=json.loads(bundle["host"]["host_class_json"]),
    )
    assert evaluation.eligibility_status == "rejected"
    assert EligibilityReasonCode.PROGRAM_IDENTITY_MISMATCH.value in evaluation.rejection_reason_codes


def test_active_host_class_invalidation_rejection(shadow_env):
    profile_id = _seed_verified_profile()
    bundle = _bundle(profile_id)
    host_id = bundle["profile"]["host_compatibility_class_id"]
    insert_invalidation(
        profile_id=profile_id,
        scope="host_class",
        scope_key=host_id,
        rule_id="test_rule",
        reason="test",
    )
    bundle = _bundle(profile_id)
    evaluation = evaluate_candidate_eligibility(
        profile_bundle=bundle,
        program_identity_key=bundle["program"]["program_identity_key"],
        host_compatibility_class_id=host_id,
        host_payload=json.loads(bundle["host"]["host_class_json"]),
        active_invalidations=bundle["invalidations"],
    )
    assert EligibilityReasonCode.ACTIVE_HOST_CLASS_INVALIDATION.value in evaluation.rejection_reason_codes


def test_imported_trust_state_shadow_only_not_winner(shadow_env):
    profile_id = _seed_verified_profile()
    with _connect() as conn:
        ensure_profile_tables(conn)
        conn.execute(
            "UPDATE compatibility_profiles SET trust_state = 'imported' WHERE profile_id = ?",
            (profile_id,),
        )
        conn.commit()
    bundle = _bundle(profile_id)
    evaluation = evaluate_candidate_eligibility(
        profile_bundle=bundle,
        program_identity_key=bundle["program"]["program_identity_key"],
        host_compatibility_class_id=bundle["profile"]["host_compatibility_class_id"],
        host_payload=json.loads(bundle["host"]["host_class_json"]),
    )
    assert evaluation.trust_category == "shadow_observation_only"
    assert evaluation.winner_selectable is False


def test_retired_profile_not_selected_as_winner(shadow_env):
    profile_id = _seed_verified_profile()
    with _connect() as conn:
        ensure_profile_tables(conn)
        conn.execute(
            "UPDATE compatibility_profiles SET lifecycle_state = 'RETIRED' WHERE profile_id = ?",
            (profile_id,),
        )
        conn.commit()
    bundle = _bundle(profile_id)
    evaluation = evaluate_candidate_eligibility(
        profile_bundle=bundle,
        program_identity_key=bundle["program"]["program_identity_key"],
        host_compatibility_class_id=bundle["profile"]["host_compatibility_class_id"],
        host_payload=json.loads(bundle["host"]["host_class_json"]),
    )
    assert evaluation.eligibility_status == "rejected"
    ranked = rank_eligible_candidates(
        candidates=[evaluation],
        profile_bundles={profile_id: bundle},
        file_path="/tmp/game.sh",
        hardware=sample_hardware(),
    )
    winner_id, _, _, _ = select_predicted_winner(ranked, {profile_id: bundle})
    assert winner_id is None


def test_ranking_skipped_for_rejected_candidates(shadow_env):
    profile_id = _seed_verified_profile()
    bundle = _bundle(profile_id)
    rejected = evaluate_candidate_eligibility(
        profile_bundle=bundle,
        program_identity_key="wrong",
        host_compatibility_class_id=bundle["profile"]["host_compatibility_class_id"],
        host_payload=json.loads(bundle["host"]["host_class_json"]),
    )
    ranked = rank_eligible_candidates(
        candidates=[rejected],
        profile_bundles={profile_id: bundle},
        file_path="/tmp/game.sh",
        hardware=sample_hardware(),
    )
    assert ranked[0].ranking_status == "not_ranked"
    assert ranked[0].final_rank_score is None


def test_ranking_components_persisted_separately(shadow_env):
    snap = build_test_snapshot()
    profile_id = _seed_verified_profile()
    inputs = ShadowPlanningInputs(
        session_id="components-sess",
        correlation_id="corr-comp",
        file_path="/tmp/game.sh",
        executable_hash=snap.program_identity_payload["executable_hash"],
        hardware=sample_hardware(),
    )
    event_id = ProfileShadowService.create_prediction(inputs)
    candidates = load_shadow_candidates(event_id)
    winner = next(c for c in candidates if c["profile_id"] == profile_id)
    components = json.loads(winner["ranking_components_json"])
    assert "program_identity_match" in components
    assert "drift_penalty" in components
    assert "ml_component" in components


def test_drift_inspection_performs_no_mutation(shadow_env, tmp_path):
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    dimensions, result = predict_bridge_drift(
        profile_manifest={"schema": "bridge_manifest_v1", "windows_version": "win10"},
        wine_prefix=str(prefix),
    )
    assert isinstance(result, str)
    assert dimensions
    source = Path(__file__).resolve().parents[1] / "alma_bridge" / "compatibility" / "profile_shadow_drift.py"
    text = source.read_text(encoding="utf-8")
    assert "run_winetricks" not in text
    assert "set_wine_windows_version" not in text


def test_duplicate_prediction_prevented(shadow_env):
    snap = build_test_snapshot()
    _seed_verified_profile()
    inputs = ShadowPlanningInputs(
        session_id="dup-sess",
        correlation_id="corr-dup",
        file_path="/tmp/game.sh",
        executable_hash=snap.program_identity_payload["executable_hash"],
        hardware=sample_hardware(),
    )
    first = ProfileShadowService.create_prediction(inputs)
    second = ProfileShadowService.create_prediction(inputs)
    assert first == second
    with _connect() as conn:
        ensure_shadow_tables(conn)
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM compatibility_profile_shadow_predictions WHERE session_id = ?",
            ("dup-sess",),
        ).fetchone()["c"]
    assert count == 1


def test_comparison_marks_insufficient_evidence_indeterminate(shadow_env):
    snap = build_test_snapshot()
    _seed_verified_profile()
    inputs = ShadowPlanningInputs(
        session_id="indet-sess",
        correlation_id="corr-ind",
        file_path="/tmp/game.sh",
        executable_hash=snap.program_identity_payload["executable_hash"],
        hardware=sample_hardware(),
    )
    ProfileShadowService.create_prediction(inputs)
    ProfileShadowService.record_actual_outcome(
        ShadowActualInputs(
            session_id="indet-sess",
            correlation_id="corr-ind",
            terminal_session_state="FAILED",
            success=False,
        )
    )
    with _connect() as conn:
        ensure_shadow_tables(conn)
        row = conn.execute(
            "SELECT indeterminate, indeterminate_reason FROM compatibility_profile_shadow_comparisons WHERE session_id = ?",
            ("indet-sess",),
        ).fetchone()
    assert int(row["indeterminate"]) == 1


def test_shadow_modules_do_not_import_orchestrator():
    shadow_files = [
        p
        for p in SHADOW_DIR.glob("profile_shadow*.py")
        if p.is_file()
    ]
    for path in shadow_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "orchestrator" in node.module:
                pytest.fail(f"{path.name} imports orchestrator")
            if isinstance(node, ast.Import):
                if any("orchestrator" in alias.name for alias in node.names):
                    pytest.fail(f"{path.name} imports orchestrator")


def test_shadow_modules_do_not_finalize_or_transition():
    forbidden = {"finalize_session", "transition", "declare_verified_session_success"}
    shadow_files = [p for p in SHADOW_DIR.glob("profile_shadow*.py") if p.is_file()]
    for path in shadow_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = None
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if name in forbidden:
                pytest.fail(f"{path.name} calls {name}")


def test_planner_output_unchanged_with_shadow(shadow_env, tmp_path, monkeypatch):
    script = tmp_path / "ok.sh"
    script.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)

    from alma_bridge.session.services.planner import DefaultCompatibilityPlanner

    planner = DefaultCompatibilityPlanner()
    baseline = planner.plan(str(script))
    with_shadow = planner.plan(str(script))
    assert [step.strategy_id for step in baseline.steps] == [
        step.strategy_id for step in with_shadow.steps
    ]


def test_bridge_result_unchanged_when_shadow_prediction_fails(shadow_env, tmp_path, monkeypatch):
    script = tmp_path / "ok.sh"
    script.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    prefix = tmp_path / "prefix"
    prefix.mkdir()

    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator.fresh_prefix_path",
        lambda _sid: str(prefix),
    )
    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator.ProfileShadowService.create_prediction",
        lambda inputs: (_ for _ in ()).throw(RuntimeError("shadow boom")),
    )
    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator.execute_attempt",
        lambda **kwargs: {
            "success": True,
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "duration_ms": 1,
            "error_signature": None,
            "likely_causes": [],
        },
    )
    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator._persist_attempt",
        lambda *args, **kwargs: None,
    )
    orch = BridgeOrchestrator()
    result = orch.run(BridgeRequest(file_path=str(script), max_attempts=1))
    assert result.success is True


def test_bridge_result_unchanged_when_actual_persistence_fails(shadow_env, tmp_path, monkeypatch):
    script = tmp_path / "ok.sh"
    script.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    prefix = tmp_path / "prefix"
    prefix.mkdir()

    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator.fresh_prefix_path",
        lambda _sid: str(prefix),
    )
    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator.ProfileShadowService.create_prediction",
        lambda inputs: "shadow-event",
    )
    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator.ProfileShadowService.record_actual_outcome",
        lambda inputs: (_ for _ in ()).throw(RuntimeError("actual boom")),
    )
    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator.execute_attempt",
        lambda **kwargs: {
            "success": True,
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "duration_ms": 1,
            "error_signature": None,
            "likely_causes": [],
        },
    )
    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator._persist_attempt",
        lambda *args, **kwargs: None,
    )
    orch = BridgeOrchestrator()
    result = orch.run(BridgeRequest(file_path=str(script), max_attempts=1))
    assert result.success is True
    assert get_profile_counters().get("shadow_actual_persist_failed", 0) >= 0
