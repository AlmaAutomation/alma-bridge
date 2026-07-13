from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from alma_bridge.compatibility.profile_lineage import promote_candidate_snapshot
from alma_bridge.compatibility.profile_shadow import ProfileShadowService
from alma_bridge.compatibility.profile_shadow_models import ShadowActualInputs, ShadowPlanningInputs
from alma_bridge.compatibility.profile_shadow_validation_analyzer import ShadowFailureAnalyzer
from alma_bridge.compatibility.profile_shadow_validation_export import export_shadow_validation_bundle
from alma_bridge.compatibility.profile_shadow_validation_models import (
    PromotionGateThresholds,
    ShadowLabelInput,
)
from alma_bridge.compatibility.profile_shadow_validation_reporter import (
    ShadowValidationReporter,
    evaluate_promotion_gates,
    wilson_ci,
)
from alma_bridge.compatibility.profile_shadow_validation_store import (
    add_label,
    ensure_validation_tables,
    init_validation_store,
    register_validation_run,
    sync_scenario_manifest,
)
from alma_bridge.compatibility.profile_store import _connect
from alma_bridge.storage import outcomes
from tests.profile_test_helpers import build_test_snapshot, sample_hardware


@pytest.fixture
def validation_env(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profiles_enabled", True)
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profile_shadow_mode", True)
    outcomes.init_outcome_store()
    init_validation_store()
    return db


def _seed_shadow_session(session_id: str, *, success: bool = True) -> str:
    snap = build_test_snapshot(session_id=session_id)
    promote_candidate_snapshot(snap)
    inputs = ShadowPlanningInputs(
        session_id=session_id,
        correlation_id=session_id,
        file_path="/tmp/game.sh",
        executable_hash=snap.program_identity_payload["executable_hash"],
        hardware=sample_hardware(),
    )
    event_id = ProfileShadowService.create_prediction(inputs)
    assert event_id
    ProfileShadowService.record_actual_outcome(
        ShadowActualInputs(
            session_id=session_id,
            correlation_id=session_id,
            terminal_session_state="SUCCEEDED" if success else "FAILED",
            success=success,
            actual_strategy_id="native_direct" if success else None,
            failure_signature=None if success else "execution_failed",
        )
    )
    return str(event_id)


def test_metrics_exclude_indeterminate_as_negatives(validation_env):
    event_id = _seed_shadow_session("labelable-sess", success=True)
    with _connect() as conn:
        ensure_validation_tables(conn)
        conn.execute(
            """
            UPDATE compatibility_profile_shadow_comparisons
            SET indeterminate = 1, false_eligibility = 0
            WHERE shadow_event_id = ?
            """,
            (event_id,),
        )
        conn.commit()

    report = ShadowValidationReporter.generate_report()
    assert report["counts"]["indeterminate_comparisons"] == 1
    assert report["metrics"]["false_eligibility_count"] == 0
    assert report["metrics"]["false_eligibility_rate"] is None or report["metrics"]["false_eligibility_rate"] == 0.0


def test_precision_denominator_uses_labels_only(validation_env):
    event_id = _seed_shadow_session("label-sess")
    add_label(
        ShadowLabelInput(
            shadow_event_id=event_id,
            label_type="eligible_correct",
            label_source="operator",
            reviewer="tester",
            reason="confirmed",
        )
    )
    add_label(
        ShadowLabelInput(
            shadow_event_id=event_id,
            label_type="eligible_incorrect",
            label_source="operator",
            reviewer="tester",
            reason="wrong",
        )
    )
    report = ShadowValidationReporter.generate_report()
    assert report["metrics"]["eligibility_precision"] == 0.5


def test_scenario_category_breakdown(validation_env):
    sync_scenario_manifest()
    event_id = _seed_shadow_session("cat-sess")
    register_validation_run(
        session_id="cat-sess",
        scenario_id="A_stable_repeat_success",
        program_kind="native_script",
        application_family="generic",
    )
    report = ShadowValidationReporter.generate_report()
    bucket = report["breakdowns"]["by_scenario_category"]
    assert "A_stable_repeat_success" in bucket


def test_duplicate_scenario_labels_prevented(validation_env):
    sync_scenario_manifest()
    _seed_shadow_session("dup-reg-sess")
    register_validation_run(session_id="dup-reg-sess", scenario_id="A_stable_repeat_success")
    register_validation_run(session_id="dup-reg-sess", scenario_id="A_stable_repeat_success")
    with _connect() as conn:
        ensure_validation_tables(conn)
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM compatibility_profile_shadow_validation_runs WHERE session_id = ?",
            ("dup-reg-sess",),
        ).fetchone()["c"]
    assert count == 1


def test_prediction_immutable_after_labeling(validation_env):
    event_id = _seed_shadow_session("imm-label-sess")
    with _connect() as conn:
        ensure_validation_tables(conn)
        row_before = conn.execute(
            "SELECT * FROM compatibility_profile_shadow_predictions WHERE shadow_event_id = ?",
            (event_id,),
        ).fetchone()
    add_label(
        ShadowLabelInput(
            shadow_event_id=event_id,
            label_type="winner_correct",
            label_source="operator",
            reviewer="tester",
            reason="ok",
        )
    )
    with _connect() as conn:
        row_after = conn.execute(
            "SELECT * FROM compatibility_profile_shadow_predictions WHERE shadow_event_id = ?",
            (event_id,),
        ).fetchone()
    assert dict(row_before) == dict(row_after)


def test_promotion_gate_fails_without_diversity(validation_env):
    _seed_shadow_session("only-one")
    report = ShadowValidationReporter.generate_report()
    gates = report["promotion_gates"]
    assert gates["promotion_ready"] is False
    assert gates["checks"]["min_comparisons"]["passed"] is False


def test_aggregate_success_cannot_hide_failing_category(validation_env):
    sync_scenario_manifest()
    thresholds = PromotionGateThresholds(min_comparisons=1, min_scenario_categories=1)
    breakdowns = {
        "by_scenario_category": {
            "D_incompatible_host_drift": {
                "labelable": 5,
                "false_eligibility": 2,
                "false_eligibility_rate": 0.4,
                "strategy_agreement": 0,
                "strategy_disagreement": 5,
                "strategy_agreement_rate": 0.0,
            }
        }
    }
    gates = evaluate_promotion_gates(
        counts={"comparisons_completed": 10, "indeterminate_comparisons": 0},
        metrics={
            "eligibility_precision": 0.99,
            "false_eligibility_rate": 0.01,
            "drift_false_positive_rate": 0.01,
            "strategy_agreement_rate": 0.95,
            "bridge_family_agreement_rate": 0.95,
            "rank_agreement_rate": 0.9,
            "profile_creation_duplicate_rate": 0.0,
        },
        diversity={
            "scenario_category_count": 5,
            "program_kind_count": 3,
            "drift_scenarios": 10,
            "rejection_scenarios": 10,
        },
        breakdowns=breakdowns,
        thresholds=thresholds,
    )
    assert gates["aggregate_passed"] is True
    assert gates["category_passed"] is False
    assert gates["promotion_ready"] is False


def test_sanitized_export_excludes_paths_and_secrets(validation_env):
    event_id = _seed_shadow_session("export-sess")
    bundle = export_shadow_validation_bundle(shadow_event_id=event_id)
    text = json.dumps(bundle)
    assert "/home/" not in text
    assert "/Users/" not in text
    assert "username" not in text or "<redacted>" in text


def test_reporter_is_read_only_ast():
    source = Path(__file__).resolve().parents[1] / "alma_bridge" / "compatibility" / "profile_shadow_validation_reporter.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    forbidden = {"finalize_session", "transition", "plan(", "execute_attempt"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = ""
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            assert name not in {"finalize_session", "transition"}


def test_wilson_ci_returns_none_for_zero_sample():
    assert wilson_ci(0, 0) is None


def test_failure_analyzer_records_false_eligibility(validation_env):
    event_id = _seed_shadow_session("fail-sess", success=False)
    with _connect() as conn:
        ensure_validation_tables(conn)
        conn.execute(
            """
            UPDATE compatibility_profile_shadow_comparisons
            SET false_eligibility = 1, indeterminate = 0
            WHERE shadow_event_id = ?
            """,
            (event_id,),
        )
        conn.commit()
    recorded = ShadowFailureAnalyzer.analyze_and_record()
    assert recorded
    report = ShadowValidationReporter.generate_report()
    assert report["failure_analyses"]
