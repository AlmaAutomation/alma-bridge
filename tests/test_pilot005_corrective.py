from __future__ import annotations

import json
from pathlib import Path

import pytest

from alma_bridge.compatibility.profile_candidate import build_bridge_manifest
from alma_bridge.compatibility.profile_creation import ProfileCandidateService, VerifiedAttemptInputs
from alma_bridge.compatibility.profile_manifest_capture import (
    MANIFEST_CAPTURE_VERSION,
    capture_verified_manifest_context,
    components_identity_key,
    manifest_reconstruction_eligible,
    normalize_component_list,
)
from alma_bridge.compatibility.profile_shadow_ranking_explanation import (
    RankingSelectionReasonCode,
    explain_ranking_selection,
)
from alma_bridge.compatibility.profile_shadow_validation_reporter import ShadowValidationReporter
from alma_bridge.compatibility.profile_shadow_validation_scope import (
    CONTROLLED_DUPLICATE_FIXTURE_IDS,
    ValidationEvidenceScope,
    build_pilot004_evidence_scope,
    comparison_in_scope,
    load_evidence_quality_review,
)
from alma_bridge.schemas.models import AttemptRecord
from alma_bridge.validation.campaign_evidence import (
    DB_RECOVERED,
    EVIDENCE_PERSISTENCE_INCOMPLETE,
    persist_run_evidence,
    prepare_run_evidence_paths,
    recover_run_evidence_from_db,
)
from alma_bridge.validation.prefix_drift import (
    COMPONENT_MARKERS,
    read_prefix_installed_components,
    remove_component_from_prefix,
)
from tests.profile_test_helpers import build_test_snapshot, sample_hardware


@pytest.fixture
def validation_env(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profiles_enabled", True)
    monkeypatch.setattr("alma_bridge.config.settings.compatibility_profile_shadow_mode", True)
    from alma_bridge.storage import outcomes
    from alma_bridge.compatibility.profile_shadow_validation_store import init_validation_store

    outcomes.init_outcome_store()
    init_validation_store()
    return db

REPO = Path(__file__).resolve().parents[1]


def test_pilot004_evidence_quality_review_immutable():
    review_path = REPO / "data/validation/campaigns/pilot-004-evidence-quality-review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    assert review["immutable"] is True
    assert review["classification"] == "COMPLETED_NOT_PROMOTION_READY"
    by_run = {r["run_number"]: r for r in review["runs"]}
    assert by_run[9]["classification"] == "exploratory_only"
    assert by_run[10]["classification"] == "promotion_eligible_evidence"
    assert all(
        by_run[n]["classification"] == "promotion_eligible_evidence"
        for n in range(1, 9)
    )


def test_build_pilot004_scope_excludes_run9():
    scope = build_pilot004_evidence_scope()
    assert scope.campaign_id == "shadow-validation-pilot-004"
    assert "c9b1b0c1-8e64-4910-bf68-6aae71cdeaba" in scope.excluded_session_id_set
    assert "9cd8a95c-853b-41e2-aa46-119236c02ef7" not in scope.included_shadow_event_id_set


def test_historical_comparison_excluded_from_campaign_scope():
    scope = ValidationEvidenceScope(
        campaign_id="shadow-validation-pilot-004",
        included_shadow_event_ids=["event-a"],
        included_session_ids=["sess-a"],
    )
    historical = {"shadow_event_id": "event-historical"}
    in_scope = {"shadow_event_id": "event-a"}
    assert comparison_in_scope(comparison=historical, scope=scope) is False
    assert comparison_in_scope(
        comparison=in_scope,
        scope=scope,
        validation_run={"session_id": "sess-a"},
    ) is True


def test_controlled_duplicate_fixture_excluded_from_scope():
    scope = build_pilot004_evidence_scope()
    assert "B_redundant_different_profile" in scope.excluded_setup_fixture_ids
    assert CONTROLLED_DUPLICATE_FIXTURE_IDS == frozenset({"B_redundant_different_profile"})


def test_scoped_gates_include_numerator_denominator(validation_env, monkeypatch):
    from alma_bridge.compatibility.profile_lineage import promote_candidate_snapshot
    from alma_bridge.compatibility.profile_shadow import ProfileShadowService
    from alma_bridge.compatibility.profile_shadow_models import ShadowActualInputs, ShadowPlanningInputs
    from alma_bridge.compatibility.profile_shadow_validation_store import register_validation_run

    event_ids = []
    for idx in range(3):
        sid = f"scoped-sess-{idx}"
        snap = build_test_snapshot(session_id=sid)
        promote_candidate_snapshot(snap)
        event_id = ProfileShadowService.create_prediction(
            ShadowPlanningInputs(
                session_id=sid,
                correlation_id=sid,
                file_path="/tmp/game.sh",
                executable_hash=snap.program_identity_payload["executable_hash"],
                hardware=sample_hardware(),
            )
        )
        assert event_id
        ProfileShadowService.record_actual_outcome(
            ShadowActualInputs(
                session_id=sid,
                correlation_id=sid,
                terminal_session_state="SUCCEEDED",
                success=True,
                actual_strategy_id="native_direct",
            )
        )
        register_validation_run(
            session_id=sid,
            scenario_id="A_stable_repeat_success",
            program_kind="pe_windows_gui",
            application_family="test",
        )
        event_ids.append(str(event_id))

    scope = ValidationEvidenceScope(
        campaign_id="test-scope",
        included_shadow_event_ids=event_ids[:2],
        included_session_ids=["scoped-sess-0", "scoped-sess-1"],
    )
    report = ShadowValidationReporter.generate_report(scope=scope)
    gates = report["promotion_gates"]["checks"]
    assert gates["min_comparisons"]["numerator"] == gates["min_comparisons"]["actual"]
    assert gates["min_comparisons"]["denominator"] == gates["min_comparisons"]["actual"]
    assert len(gates["min_comparisons"]["included_ids"]) == gates["min_comparisons"]["actual"]


def test_global_gates_differ_from_scoped_when_historical_present(validation_env, monkeypatch):
    from alma_bridge.compatibility.profile_lineage import promote_candidate_snapshot
    from alma_bridge.compatibility.profile_shadow import ProfileShadowService
    from alma_bridge.compatibility.profile_shadow_models import ShadowActualInputs, ShadowPlanningInputs

    for idx in range(4):
        sid = f"hist-sess-{idx}"
        snap = build_test_snapshot(session_id=sid)
        promote_candidate_snapshot(snap)
        ProfileShadowService.create_prediction(
            ShadowPlanningInputs(
                session_id=sid,
                correlation_id=sid,
                file_path="/tmp/game.sh",
                executable_hash=snap.program_identity_payload["executable_hash"],
                hardware=sample_hardware(),
            )
        )
        ProfileShadowService.record_actual_outcome(
            ShadowActualInputs(
                session_id=sid,
                correlation_id=sid,
                terminal_session_state="SUCCEEDED",
                success=True,
                actual_strategy_id="native_direct",
            )
        )

    global_report = ShadowValidationReporter.generate_report()
    scoped = ValidationEvidenceScope(
        campaign_id="test",
        included_shadow_event_ids=[],
        included_session_ids=["hist-sess-0"],
    )
    scoped_report = ShadowValidationReporter.generate_report(scope=scoped)
    assert global_report["counts"]["comparisons_completed"] >= scoped_report["counts"]["comparisons_completed"]


def test_manifest_capture_from_prefix_with_corefonts(tmp_path):
    prefix = tmp_path / "prefix"
    for marker in COMPONENT_MARKERS["corefonts"]:
        path = prefix / marker
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"font")
    record = AttemptRecord(
        attempt_number=1,
        strategy_id="wine_host",
        remediation_id=None,
        runtime="wine",
        command=["wine", "notepad.exe"],
        env={"WINEPREFIX": str(prefix)},
        mode="host",
        success=True,
        exit_code=0,
        phase="native",
    )
    captured = capture_verified_manifest_context(record=record)
    assert captured.winetricks_components == ["corefonts"]
    assert captured.component_capture_complete is True
    assert captured.manifest_capture_version == MANIFEST_CAPTURE_VERSION


def test_profile_creation_stores_corefonts(tmp_path):
    prefix = tmp_path / "prefix"
    for marker in COMPONENT_MARKERS["corefonts"]:
        path = prefix / marker
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"font")
    record = AttemptRecord(
        attempt_number=1,
        strategy_id="wine_host",
        remediation_id=None,
        runtime="wine",
        command=["wine", "notepad.exe"],
        env={"WINEPREFIX": str(prefix)},
        mode="host",
        success=True,
        exit_code=0,
        phase="native",
    )
    snap = ProfileCandidateService.build_snapshot(
        VerifiedAttemptInputs(
            session_id="sess-corefonts",
            file_path="/tmp/notepad.exe",
            executable_hash="abc123",
            hardware=sample_hardware(),
            record=record,
            verification_payload={"success_policy": {"policy_id": "bridge_aggregate_v1"}},
        )
    )
    manifest = snap.bridge_manifest
    assert manifest["installed_components"] == ["corefonts"]
    assert manifest["manifest_capture_version"] == MANIFEST_CAPTURE_VERSION


def test_component_missing_against_stored_manifest(tmp_path):
    prefix = tmp_path / "prefix"
    for marker in COMPONENT_MARKERS["corefonts"]:
        path = prefix / marker
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"font")
    manifest = build_bridge_manifest(
        runtime="wine",
        strategy_id="wine_host",
        windows_version="win10",
        prefix_architecture="win64",
        remediation_protocol=[],
        env={},
        winetricks_components=["corefonts"],
        manifest_capture_version=MANIFEST_CAPTURE_VERSION,
        component_capture_complete=True,
    )
    remove_component_from_prefix(str(prefix), "corefonts")
    observed = read_prefix_installed_components(str(prefix))
    assert "corefonts" not in observed
    assert manifest["installed_components"] == ["corefonts"]


def test_component_order_identity_stable():
    assert components_identity_key(["corefonts", "vcrun2019"]) == components_identity_key(
        ["vcrun2019", "corefonts"]
    )
    assert normalize_component_list(["b", "a"]) == ["a", "b"]


def test_legacy_manifest_not_reconstruction_eligible():
    ok, reason = manifest_reconstruction_eligible({"schema": "bridge_manifest_v1"})
    assert ok is False
    assert reason == "MANIFEST_CAPTURE_VERSION_MISSING"


def test_prepare_run_evidence_paths_creates_directories(tmp_path):
    evidence_root = tmp_path / "evidence"
    paths = prepare_run_evidence_paths(evidence_root=evidence_root, run_number=10)
    assert paths.run_dir.is_dir()
    assert paths.response_path.parent == paths.run_dir


def test_persist_run_evidence_atomic(tmp_path):
    evidence_root = tmp_path / "evidence"
    paths = prepare_run_evidence_paths(evidence_root=evidence_root, run_number=3)
    meta = persist_run_evidence(
        paths=paths,
        response={"session_id": "sess-3", "success": True},
        extra={"note": "test"},
        session_id="sess-3",
    )
    assert paths.response_path.is_file()
    assert paths.evidence_path.is_file()
    assert meta["status"] == "complete"


def test_db_recovery_without_reexecution(tmp_path):
    evidence_root = tmp_path / "evidence"
    paths = prepare_run_evidence_paths(evidence_root=evidence_root, run_number=10)
    meta = recover_run_evidence_from_db(
        paths=paths,
        response={"session_id": "f696b987-16a2-49cc-9b89-e46446ced9d2", "success": False},
        extra={"recovery": True},
        session_id="f696b987-16a2-49cc-9b89-e46446ced9d2",
    )
    assert meta["recovery_mode"] == DB_RECOVERED
    assert paths.response_path.is_file()


def test_evidence_persistence_incomplete_on_write_failure(tmp_path, monkeypatch):
    evidence_root = tmp_path / "evidence"
    paths = prepare_run_evidence_paths(evidence_root=evidence_root, run_number=7)
    original_write = Path.write_text

    def _fail_response_write(self, *args, **kwargs):
        if self.name == "response.json":
            raise OSError("disk full")
        return original_write(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", _fail_response_write)
    with pytest.raises(OSError):
        persist_run_evidence(paths=paths, response={"session_id": "x"})
    meta = json.loads(paths.metadata_path.read_text(encoding="utf-8"))
    assert meta["status"] == EVIDENCE_PERSISTENCE_INCOMPLETE


class _Ranked:
    def __init__(self, profile_id: str, score: float, recency: float, revision: int = 1):
        self.profile_id = profile_id
        self.profile_revision = revision
        self.eligibility_status = "eligible"
        self.ranking_status = "ranked"
        self.final_rank_score = score
        self.winner_selectable = True
        self.ranking_components = {
            "recency": recency,
            "reuse_success_rate": 0.5,
            "verification_confidence": 0.9,
            "failure_penalty": 0.0,
        }


def test_recency_only_ranking_not_active_reuse_eligible():
    bundles = {
        "a": {"bridge": {"manifest_json": {"installed_components": [], "environment": {}}}},
        "b": {
            "bridge": {
                "manifest_json": {
                    "installed_components": [],
                    "environment": {"WINEDLLOVERRIDES": "winemenubuilder.exe=d"},
                }
            }
        },
    }
    ranked = [_Ranked("a", 0.9997, 0.995), _Ranked("b", 1.0, 0.9999, revision=4)]
    explanation = explain_ranking_selection(
        ranked_candidates=ranked,
        profile_bundles=bundles,
        winner_profile_id="b",
        winner_revision=4,
    )
    assert explanation is not None
    assert explanation.ranking_reason_code == RankingSelectionReasonCode.RECENCY_ONLY_TIEBREAK
    assert explanation.active_reuse_eligible is False
    assert explanation.technical_superiority_established is False


def test_load_evidence_quality_review():
    review = load_evidence_quality_review()
    assert review["runs"]
    assert any(r["run_number"] == 9 for r in review["runs"])
