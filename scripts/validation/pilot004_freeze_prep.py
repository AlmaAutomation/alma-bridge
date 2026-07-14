#!/usr/bin/env python3
"""Pilot-004 freeze preparation: setup, dry-runs, audits, evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "data/validation/evidence/pilot-004"
PILOT_ROOT = Path.home() / ".local/share/alma-bridge/prefixes/validation/pilot-004"
SNAP_ROOT = PILOT_ROOT / "snapshots"
DB_PATH = REPO / "data/outcomes.db"
CANONICAL_T2 = "a5576257-65b5-485f-a966-8273bccd8146"
CANDIDATE2_T2 = "b2a24a3b-c93c-47f1-826e-cd8d967528cd"
T2_HASH = "108168df2b9679c5ef4004a5fa63990c99b189661ee3cac4bb8f9dd467ad6d69"
T32_HASH = "503665cbf1e3be907387c2b76beb25bcdef7d326738adf6f06ff53b9984a2684"
CORRECTIVE_SHA = "68ef1381cff491edd1b743f2b1624845d79bb7f7"
PILOT003_SNAPS = Path.home() / ".local/share/alma-bridge/prefixes/validation/pilot-003/snapshots"
EXCLUDED = {
    "425f8664-7ddd-4a99-b984-435051027e8f",
    "bebf5c5f-6719-4ac2-8e75-29ac6c839bf3",
    "6aec0dd2-e298-4173-aec3-603e2aae691b",
    "9b0cf7ff-aca8-44ee-b354-28505ac3c60d",
}
SETUP_T2B_ENV = {"WINEDLLOVERRIDES": "winemenubuilder.exe=d"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_tree(prefix: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(prefix.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(prefix)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _env() -> Dict[str, str]:
    return {
        **os.environ,
        "PYTHONPATH": str(REPO),
        "ALMA_BRIDGE_COMPATIBILITY_PROFILES_ENABLED": "true",
        "ALMA_BRIDGE_COMPATIBILITY_PROFILE_CREATION_ENABLED": "true",
        "ALMA_BRIDGE_COMPATIBILITY_PROFILE_SHADOW_MODE": "true",
        "ALMA_BRIDGE_COMPATIBILITY_PROFILE_REUSE_ENABLED": "false",
        "ALMA_BRIDGE_OPERATOR_ENABLED": "false",
        "ALMA_BRIDGE_OPERATOR_ALLOW_MUTATIONS": "false",
        "ALMA_BRIDGE_VALIDATION_CAMPAIGN_MODE": "true",
        "ALMA_BRIDGE_VALIDATION_CAMPAIGN_ID": "shadow-validation-pilot-004",
        "ALMA_BRIDGE_VALIDATION_CAMPAIGN_DISPOSABLE_ROOT": str(PILOT_ROOT),
        "ALMA_BRIDGE_VALIDATION_CAMPAIGN_SOURCE_SNAPSHOT": str(SNAP_ROOT),
    }


def _apply_env() -> None:
    os.environ.update(_env())
    sys.path.insert(0, str(REPO))


def _load_bundle(profile_id: str) -> Dict[str, Any]:
    from alma_bridge.compatibility.profile_store import load_profile_bundle

    bundle = load_profile_bundle(profile_id)
    if not bundle:
        raise RuntimeError(f"profile not found: {profile_id}")
    return bundle


def _manifest_fields(bundle: Dict[str, Any]) -> Dict[str, Any]:
    manifest = json.loads(bundle["bridge"]["manifest_json"])
    return {
        "profile_id": bundle["profile"]["profile_id"],
        "profile_revision": bundle["profile"]["profile_revision"],
        "profile_lineage_key": bundle["profile"]["lineage_key"],
        "program_identity_key": bundle["program"]["program_identity_key"],
        "executable_hash": bundle["program"]["executable_hash"],
        "host_compatibility_class_id": bundle["host"]["host_compatibility_class_id"],
        "bridge_family_key": bundle["bridge"]["bridge_family_key"],
        "bridge_manifest_hash": bundle["bridge"]["bridge_manifest_hash"],
        "verification_binding_key": bundle["verification"]["verification_binding_key"],
        "trust_state": bundle["profile"]["trust_state"],
        "source_session_id": bundle["profile"]["source_session_id"],
        "manifest": manifest,
    }


def _clone_prefix(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest, symlinks=True)
    subprocess.run(["chmod", "-R", "u+w", str(dest)], check=False)


def _freeze_prefix(prefix: Path) -> None:
    subprocess.run(["chmod", "-R", "a-w", str(prefix)], check=False)


def _wine_version() -> str:
    proc = subprocess.run(["wine", "--version"], capture_output=True, text=True, check=False)
    return (proc.stdout or proc.stderr or "unknown").strip().splitlines()[0]


def setup_t2b_alt_manifest(force: bool = False) -> Dict[str, Any]:
    """SETUP-T2-B-alt-manifest via normal Bridge with material env delta."""
    existing = EVIDENCE / "setup-t2b-alt-manifest.json"
    if existing.exists() and not force:
        return json.loads(existing.read_text())

    bundle2 = _load_bundle(CANDIDATE2_T2)
    if bundle2 and not force:
        before = _manifest_fields(_load_bundle(CANONICAL_T2))
        after = _manifest_fields(bundle2)
        delta = {
            k: {"candidate1": before["manifest"].get(k), "candidate2": after["manifest"].get(k)}
            for k in sorted(set(before["manifest"]) | set(after["manifest"]))
            if before["manifest"].get(k) != after["manifest"].get(k)
        }
        report = {
            "setup_id": "SETUP-T2-B-alt-manifest",
            "excluded_from_scenario_metrics": True,
            "setup_session_id": after["source_session_id"],
            "candidate1": before,
            "candidate2": after,
            "manifest_delta": delta,
            "material_difference_justification": (
                "WINEDLLOVERRIDES winemenubuilder.exe=d is a stable Wine DLL load-order "
                "compatibility configuration captured in bridge manifest environment. "
                "It is not WINEPREFIX, path, hostname, or session ephemeral state."
            ),
            "payload": {"profile_id": after["profile_id"], "session_id": after["source_session_id"], "success": True},
            "recovered_from_db": True,
        }
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_text(json.dumps(report, indent=2, sort_keys=True))
        return report

    from alma_bridge.validation.setup_preflight import run_setup_target

    prefix = PILOT_ROOT / "setup/t2-notepad64-b-alt"
    prefix.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        f'WINEPREFIX="{prefix}" WINEDEBUG=-all wineboot -i',
        shell=True,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    exe = prefix / "drive_c/windows/system32/notepad.exe"
    if not exe.exists():
        raise RuntimeError(f"notepad missing after wineboot: {exe}")

    before = _manifest_fields(_load_bundle(CANONICAL_T2))
    payload = run_setup_target(
        setup_id="SETUP-T2-B-alt-manifest",
        exe_path=exe,
        wine_prefix=prefix,
        env=SETUP_T2B_ENV,
    )
    if not payload.get("success"):
        raise RuntimeError(f"SETUP-T2-B failed: {payload}")
    profile_id = payload.get("profile_id")
    if not profile_id:
        raise RuntimeError(f"no profile promoted: {payload}")
    if profile_id == CANONICAL_T2:
        raise RuntimeError(
            "SETUP-T2-B attached to Candidate 1 — manifest delta insufficient; redesign required"
        )

    after = _manifest_fields(_load_bundle(profile_id))
    delta = {
        k: {"candidate1": before["manifest"].get(k), "candidate2": after["manifest"].get(k)}
        for k in sorted(set(before["manifest"]) | set(after["manifest"]))
        if before["manifest"].get(k) != after["manifest"].get(k)
    }
    report = {
        "setup_id": "SETUP-T2-B-alt-manifest",
        "excluded_from_scenario_metrics": True,
        "setup_session_id": payload["session_id"],
        "candidate1": before,
        "candidate2": after,
        "manifest_delta": delta,
        "material_difference_justification": (
            "WINEDLLOVERRIDES winemenubuilder.exe=d is a stable Wine DLL load-order "
            "compatibility configuration captured in bridge manifest environment. "
            "It is not WINEPREFIX, path, hostname, or session ephemeral state."
        ),
        "payload": payload,
    }
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text(json.dumps(report, indent=2, sort_keys=True))
    return report


def run_j_audit(candidate2_id: str = CANDIDATE2_T2) -> Dict[str, Any]:
    from alma_bridge.compatibility.profile_shadow_eligibility import evaluate_candidate_eligibility
    from alma_bridge.compatibility.expected_verification_contract import expected_verification_contract_for_kind
    from alma_bridge.compatibility.profile_shadow_ranking import (
        RANKING_FORMULA_ID,
        RANKING_FORMULA_VERSION,
        rank_eligible_candidates,
        select_predicted_winner,
    )
    from alma_bridge.compatibility.profile_host_class import (
        build_host_compatibility_class_payload,
        build_host_compatibility_class_id,
    )
    from alma_bridge.hardware.profiler import profile_hardware

    hardware = profile_hardware()
    host_payload = build_host_compatibility_class_payload(hardware, program_needs_gpu=True)
    host_class_id = build_host_compatibility_class_id(host_payload)
    expected = expected_verification_contract_for_kind({"program_kind": "pe_windows_gui"})

    candidates_report = []
    bundles = {}
    evaluations = []
    for pid in [CANONICAL_T2, candidate2_id]:
        bundle = _load_bundle(pid)
        bundles[pid] = bundle
        ev = evaluate_candidate_eligibility(
            profile_bundle=bundle,
            program_identity_key=bundle["program"]["program_identity_key"],
            host_compatibility_class_id=host_class_id,
            host_payload=host_payload,
            expected_verification=expected,
            active_invalidations=bundle.get("invalidations"),
        )
        evaluations.append(ev)
        candidates_report.append(
            {
                "profile_id": pid,
                "profile_revision": bundle["profile"]["profile_revision"],
                "bridge_manifest_hash": bundle["bridge"]["bridge_manifest_hash"],
                "eligibility_status": ev.eligibility_status,
                "rejection_reason_codes": ev.rejection_reason_codes,
                "trust_category": ev.trust_category,
                "winner_selectable": ev.winner_selectable,
                "ranking_components": ev.ranking_components,
            }
        )

    ranked = rank_eligible_candidates(
        candidates=evaluations,
        profile_bundles=bundles,
        file_path=str(PILOT003_SNAPS / "source-t2-notepad64-20260714T040638Z/drive_c/windows/system32/notepad.exe"),
        hardware=hardware,
    )
    winner_id, winner_rev, _, _ = select_predicted_winner(ranked, bundles)
    ranked_report = [
        {
            "profile_id": e.profile_id,
            "final_rank_score": e.final_rank_score,
            "ranking_components": e.ranking_components,
            "ranking_status": e.ranking_status,
        }
        for e in ranked
        if e.eligibility_status == "eligible"
    ]
    audit = {
        "campaign_id": "shadow-validation-pilot-004",
        "executable_hash": T2_HASH,
        "candidates": candidates_report,
        "distinct_manifest_hashes": len({c["bridge_manifest_hash"] for c in candidates_report}),
        "meaningful_ranking_difference": any(
            ranked_report[i]["ranking_components"] != ranked_report[j]["ranking_components"]
            for i in range(len(ranked_report))
            for j in range(i + 1, len(ranked_report))
        ) if len(ranked_report) >= 2 else False,
        "ranking_formula_id": RANKING_FORMULA_ID,
        "ranking_formula_version": RANKING_FORMULA_VERSION,
        "ranked_eligible": ranked_report,
        "predicted_winner_profile_id": winner_id,
        "predicted_winner_revision": winner_rev,
    }
    out = EVIDENCE / "run-j-eligibility-ranking-audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(audit, indent=2, sort_keys=True))
    (REPO / "data/validation/campaigns/pilot-004-eligibility-audit.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True)
    )
    return audit


def duplicate_metric_audit() -> Dict[str, Any]:
    from alma_bridge.compatibility.profile_shadow_comparison import build_shadow_comparison_metrics

    def case(name: str, **kwargs) -> Dict[str, Any]:
        m = build_shadow_comparison_metrics(**kwargs)
        return {"case": name, "duplicate_predicted_lineage": m["duplicate_predicted_lineage"], "metrics": m}

    cases = [
        case(
            "A_same_promoted_profile",
            prediction={"selected_profile_id": CANONICAL_T2, "predicted_strategy_id": "wine_host"},
            candidates=[{"profile_id": CANONICAL_T2, "eligibility_status": "eligible", "bridge_family_match_dimensions_json": "{}"}],
            actual={"actual_success": True, "actual_strategy_id": "wine_host"},
            profile_candidate_id="b681ac4b-17ad-481b-9c12-49da224c6c82",
        ),
        case(
            "B_redundant_different_profile",
            prediction={"selected_profile_id": CANONICAL_T2, "predicted_strategy_id": "wine_host"},
            candidates=[{"profile_id": CANONICAL_T2, "eligibility_status": "eligible", "bridge_family_match_dimensions_json": "{}"}],
            actual={"actual_success": True, "actual_strategy_id": "wine_host"},
            profile_candidate_id="fff25b6c-4fb6-420e-9918-a496d76db9bc",
        ),
        case(
            "D_attachment_no_duplicate",
            prediction={"selected_profile_id": CANONICAL_T2, "predicted_strategy_id": "wine_host"},
            candidates=[{"profile_id": CANONICAL_T2, "eligibility_status": "eligible", "bridge_family_match_dimensions_json": "{}"}],
            actual={"actual_success": True, "actual_strategy_id": "wine_host"},
            profile_candidate_id=None,
        ),
    ]

    legacy_cases = []
    for pid in sorted(EXCLUDED):
        m = build_shadow_comparison_metrics(
            prediction={"selected_profile_id": pid, "predicted_strategy_id": "wine_host"},
            candidates=[{"profile_id": pid, "eligibility_status": "rejected", "bridge_family_match_dimensions_json": "{}"}],
            actual={"actual_success": False, "failure_signature": "excluded_fixture"},
            profile_candidate_id=None,
        )
        legacy_cases.append({"profile_id": pid, "duplicate_predicted_lineage": m["duplicate_predicted_lineage"]})

    audit = {
        "cases": cases,
        "legacy_exclusion_cases": legacy_cases,
        "legacy_exclusion_note": (
            "Excluded legacy profiles are not winner-selectable and do not enter "
            "labelable comparison denominators during campaign execution."
        ),
        "passed": (
            cases[0]["duplicate_predicted_lineage"] == 0
            and cases[1]["duplicate_predicted_lineage"] == 1
            and cases[2]["duplicate_predicted_lineage"] == 0
            and all(c["duplicate_predicted_lineage"] == 0 for c in legacy_cases)
        ),
    }
    out = EVIDENCE / "duplicate-metric-audit.json"
    out.write_text(json.dumps(audit, indent=2, sort_keys=True))
    return audit


def _snapshot_record(
    *,
    key: str,
    dest: Path,
    exe: Path,
    arch: str,
    exe_hash: str,
    wine_ver: str,
    ts: str,
    components: List[str],
    bridge_manifest_hash: Optional[str],
) -> Dict[str, Any]:
    return {
        "snapshot_key": key,
        "path": str(dest),
        "realpath": os.path.realpath(dest),
        "aggregate_sha256": _sha256_tree(dest),
        "wine_version": wine_ver,
        "prefix_architecture": arch,
        "windows_version": "win10",
        "installed_components": components,
        "target_executable_path": str(exe.relative_to(dest)),
        "target_executable_sha256": exe_hash,
        "created_at_utc": ts,
        "immutable": True,
        "bridge_manifest_hash": bridge_manifest_hash,
        "source_provenance": "pilot-003 snapshot clone + pilot-004 freeze capture",
    }


def capture_source_snapshots() -> Dict[str, Any]:
    from alma_bridge.execution.preflight import run_winetricks
    from alma_bridge.validation.prefix_drift import read_prefix_installed_components

    ts = _now()
    wine_ver = _wine_version()
    src_t2 = PILOT003_SNAPS / "source-t2-notepad64-20260714T040638Z"
    src_t3_wp = PILOT003_SNAPS / "source-t3-wordpad64-20260714T040638Z"
    src_t32 = PILOT003_SNAPS / "source-t3-notepad32-20260714T040638Z"
    SNAP_ROOT.mkdir(parents=True, exist_ok=True)
    records = []
    t2_bundle = _load_bundle(CANONICAL_T2)
    t2_manifest_hash = t2_bundle["bridge"]["bridge_manifest_hash"]

    t2_dest = SNAP_ROOT / f"source-t2-notepad64-{ts}"
    _clone_prefix(src_t2, t2_dest)
    _freeze_prefix(t2_dest)
    t2_exe = t2_dest / "drive_c/windows/system32/notepad.exe"
    records.append(
        _snapshot_record(
            key="t2_notepad64",
            dest=t2_dest,
            exe=t2_exe,
            arch="win64",
            exe_hash=T2_HASH,
            wine_ver=wine_ver,
            ts=ts,
            components=read_prefix_installed_components(str(t2_dest)),
            bridge_manifest_hash=t2_manifest_hash,
        )
    )

    core_dest = SNAP_ROOT / f"source-t2-notepad64-corefonts-{ts}"
    _clone_prefix(t2_dest, core_dest)
    subprocess.run(["chmod", "-R", "u+w", str(core_dest)], check=False)
    ok, msg = run_winetricks(str(core_dest), ["corefonts"], timeout_sec=900)
    if not ok:
        raise RuntimeError(f"corefonts install failed: {msg}")
    _freeze_prefix(core_dest)
    records.append(
        _snapshot_record(
            key="t2_notepad64_corefonts",
            dest=core_dest,
            exe=core_dest / "drive_c/windows/system32/notepad.exe",
            arch="win64",
            exe_hash=T2_HASH,
            wine_ver=wine_ver,
            ts=ts,
            components=read_prefix_installed_components(str(core_dest)),
            bridge_manifest_hash=t2_manifest_hash,
        )
    )

    t3_wp_dest = SNAP_ROOT / f"source-t3-wordpad64-{ts}"
    _clone_prefix(src_t3_wp, t3_wp_dest)
    _freeze_prefix(t3_wp_dest)
    wp_exe = t3_wp_dest / "drive_c/Program Files/Windows NT/Accessories/wordpad.exe"
    records.append(
        _snapshot_record(
            key="t3_wordpad64",
            dest=t3_wp_dest,
            exe=wp_exe,
            arch="win64",
            exe_hash=_sha256_file(wp_exe),
            wine_ver=wine_ver,
            ts=ts,
            components=read_prefix_installed_components(str(t3_wp_dest)),
            bridge_manifest_hash=None,
        )
    )

    t32_dest = SNAP_ROOT / f"source-t3-notepad32-{ts}"
    _clone_prefix(src_t32, t32_dest)
    _freeze_prefix(t32_dest)
    t32_exe = t32_dest / "drive_c/windows/syswow64/notepad.exe"
    t32_bundle = _load_bundle("9c96be17-46eb-46d7-ba0b-9c404f97bf80")
    records.append(
        _snapshot_record(
            key="t3_notepad32",
            dest=t32_dest,
            exe=t32_exe,
            arch="win32",
            exe_hash=T32_HASH,
            wine_ver=wine_ver,
            ts=ts,
            components=read_prefix_installed_components(str(t32_dest)),
            bridge_manifest_hash=t32_bundle["bridge"]["bridge_manifest_hash"],
        )
    )

    payload = {"campaign_id": "shadow-validation-pilot-004", "created_at_utc": ts, "snapshots": records}
    out = EVIDENCE / f"source-snapshots-{ts}.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    (REPO / "data/validation/campaigns/pilot-004-source-snapshots.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True)
    )
    (EVIDENCE / "source-snapshots-latest.json").write_text(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def _init_shadow() -> None:
    from alma_bridge.storage import outcomes
    from alma_bridge.compatibility.profile_shadow_store import init_shadow_store

    outcomes.init_outcome_store()
    init_shadow_store()


def _shadow_session(
    *,
    session_id: str,
    exe_path: str,
    wine_prefix: str,
    executable_hash: str = T2_HASH,
    host_overlay: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from alma_bridge.compatibility.profile_shadow import ProfileShadowService
    from alma_bridge.compatibility.profile_shadow_models import ShadowPlanningInputs
    from alma_bridge.compatibility.profile_shadow_store import load_shadow_candidates, load_shadow_prediction
    from alma_bridge.compatibility.profile_host_class import build_host_compatibility_class_payload
    from alma_bridge.hardware.profiler import profile_hardware

    hardware = profile_hardware()
    real_host = build_host_compatibility_class_payload(hardware, program_needs_gpu=True)
    effective = {**real_host, **(host_overlay or {})}
    inputs = ShadowPlanningInputs(
        session_id=session_id,
        correlation_id=session_id,
        file_path=exe_path,
        executable_hash=executable_hash,
        hardware=hardware,
        wine_prefix=wine_prefix,
        host_payload_overlay=host_overlay,
    )
    event_id = ProfileShadowService.create_prediction(inputs)
    prediction = load_shadow_prediction(session_id)
    candidates = load_shadow_candidates(str(event_id))
    return {
        "shadow_event_id": event_id,
        "session_id": session_id,
        "real_host_payload": real_host,
        "overlay_payload": host_overlay,
        "effective_host_payload": effective,
        "selected_profile_id": prediction.get("selected_profile_id") if prediction else None,
        "candidates": [
            {
                "profile_id": c["profile_id"],
                "eligibility_status": c["eligibility_status"],
                "rejection_reason_codes": json.loads(c["rejection_reason_codes_json"] or "[]"),
                "drift_prediction_result": c["drift_prediction_result"],
                "drift_dimensions": json.loads(c["drift_dimensions_json"] or "[]"),
            }
            for c in candidates
        ],
    }


def windows_drift_dry_run(snapshots: Dict[str, Any]) -> Dict[str, Any]:
    from alma_bridge.validation.prefix_drift import (
        apply_windows_version_mutation,
        read_prefix_windows_version,
        verify_windows_version,
    )

    t2 = next(s for s in snapshots["snapshots"] if s["snapshot_key"] == "t2_notepad64")
    src = Path(t2["path"])
    clone = PILOT_ROOT / "dry-run/run-06-windows-drift"
    _clone_prefix(src, clone)
    src_hash_before = _sha256_tree(src)

    baseline = read_prefix_windows_version(str(clone))
    ok, msg = apply_windows_version_mutation(str(clone), "win7")
    if not ok:
        raise RuntimeError(f"win7 mutation failed: {msg}")
    observed = read_prefix_windows_version(str(clone))
    if not verify_windows_version(str(clone), "win7"):
        raise RuntimeError(f"win7 readback failed, observed={observed}")

    exe = clone / "drive_c/windows/system32/notepad.exe"
    shadow = _shadow_session(
        session_id=f"pilot004-dry-run-06-{uuid.uuid4()}",
        exe_path=str(exe),
        wine_prefix=str(clone),
    )
    canonical = next((c for c in shadow["candidates"] if c["profile_id"] == CANONICAL_T2), None)
    drift_codes = [d.get("reason_code") for d in (canonical or {}).get("drift_dimensions", [])]

    report = {
        "run_number": 6,
        "scenario_id": "E_prefix_drift_windows",
        "dry_run_only": True,
        "source_snapshot_path": t2["path"],
        "source_snapshot_hash_before": t2["aggregate_sha256"],
        "source_snapshot_hash_after": _sha256_tree(src),
        "source_snapshot_unchanged": _sha256_tree(src) == src_hash_before,
        "disposable_clone": str(clone),
        "expected_windows_version": "win10",
        "baseline_windows_version": baseline,
        "observed_windows_version": observed,
        "shadow_prediction": shadow,
        "drift_reason_codes": drift_codes,
        "passed": (
            baseline == "win10"
            and observed == "win7"
            and "WINDOWS_VERSION_DRIFT" in drift_codes
            and _sha256_tree(src) == src_hash_before
        ),
    }
    if clone.exists():
        shutil.rmtree(clone)
    out = EVIDENCE / "dry-run-windows-drift.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True))
    return report


def component_drift_dry_run(snapshots: Dict[str, Any]) -> Dict[str, Any]:
    from alma_bridge.compatibility.profile_shadow_drift import predict_bridge_drift
    from alma_bridge.validation.prefix_drift import (
        baseline_component_set,
        remove_component_from_prefix,
        verify_component_absent,
    )

    snap = next(s for s in snapshots["snapshots"] if s["snapshot_key"] == "t2_notepad64_corefonts")
    src = Path(snap["path"])
    src_hash_before = _sha256_tree(src)
    clone = PILOT_ROOT / "dry-run/run-07-component-drift"
    _clone_prefix(src, clone)

    baseline = baseline_component_set(str(clone))
    if "corefonts" not in baseline:
        raise RuntimeError(f"corefonts missing in baseline: {baseline}")
    ok, msg = remove_component_from_prefix(str(clone), "corefonts")
    if not ok:
        raise RuntimeError(msg)
    if not verify_component_absent(str(clone), "corefonts"):
        raise RuntimeError("corefonts still present after removal")

    bundle = _load_bundle(CANONICAL_T2)
    manifest = json.loads(bundle["bridge"]["manifest_json"])
    effective_manifest = {**manifest, "installed_components": ["corefonts"]}
    drift_dims, drift_result = predict_bridge_drift(
        profile_manifest=effective_manifest,
        wine_prefix=str(clone),
    )
    drift_codes = [d.reason_code for d in drift_dims]

    exe = clone / "drive_c/windows/system32/notepad.exe"
    shadow = _shadow_session(
        session_id=f"pilot004-dry-run-07-{uuid.uuid4()}",
        exe_path=str(exe),
        wine_prefix=str(clone),
    )

    report = {
        "run_number": 7,
        "scenario_id": "E_prefix_drift_component",
        "dry_run_only": True,
        "source_snapshot_path": snap["path"],
        "source_snapshot_hash_before": snap["aggregate_sha256"],
        "source_snapshot_hash_after": _sha256_tree(src),
        "source_snapshot_unchanged": _sha256_tree(src) == src_hash_before,
        "disposable_clone": str(clone),
        "expected_components": ["corefonts"],
        "baseline_components": baseline,
        "observed_components_after_removal": baseline_component_set(str(clone)),
        "effective_manifest_for_run7": effective_manifest,
        "drift_engine": {
            "drift_result": drift_result,
            "reason_codes": drift_codes,
            "dimensions": [
                {
                    "dimension": d.dimension,
                    "status": d.status,
                    "reason_code": d.reason_code,
                    "expected": d.expected,
                    "observed": d.observed,
                }
                for d in drift_dims
            ],
        },
        "shadow_prediction": shadow,
        "passed": (
            "corefonts" in baseline
            and "corefonts" not in baseline_component_set(str(clone))
            and "COMPONENT_MISSING" in drift_codes
            and _sha256_tree(src) == src_hash_before
        ),
    }
    if clone.exists():
        shutil.rmtree(clone)
    out = EVIDENCE / "dry-run-component-drift.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True))
    return report


def known_failure_dry_run(snapshots: Dict[str, Any]) -> Dict[str, Any]:
    t2 = next(s for s in snapshots["snapshots"] if s["snapshot_key"] == "t2_notepad64")
    src = Path(t2["path"])
    src_hash_before = _sha256_tree(src)
    clone = PILOT_ROOT / "dry-run/run-09-known-failure"
    _clone_prefix(src, clone)
    exe = clone / "drive_c/windows/system32/notepad.exe"
    if not exe.is_file():
        raise RuntimeError("target executable missing in clone baseline")
    identity = {
        "executable_path": str(exe),
        "executable_sha256": _sha256_file(exe),
        "program_identity_key": _load_bundle(CANONICAL_T2)["program"]["program_identity_key"],
    }
    exe.unlink()
    absent = not exe.exists()
    report = {
        "run_number": 9,
        "scenario_id": "G_known_compatibility_failure",
        "dry_run_only": True,
        "precondition_only": True,
        "source_snapshot_path": t2["path"],
        "source_snapshot_unchanged": _sha256_tree(src) == src_hash_before,
        "disposable_clone": str(clone),
        "target_identity_before_removal": identity,
        "target_absent_confirmed": absent,
        "expected_bridge_result": "failure",
        "expected_failure_signature": "file_not_found_or_launch_error",
        "expected_terminal_state": "FAILED",
        "auto_compatibility_budget_expectation": "no_promotion; failure recorded",
        "shadow_eligibility_interpretation": "indeterminate label; no winner selection",
        "passed": absent and _sha256_tree(src) == src_hash_before,
    }
    if clone.exists():
        shutil.rmtree(clone)
    out = EVIDENCE / "dry-run-known-failure-precondition.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True))
    return report


def host_overlay_audit(snapshots: Dict[str, Any]) -> Dict[str, Any]:
    t2 = next(s for s in snapshots["snapshots"] if s["snapshot_key"] == "t2_notepad64")
    t32 = next(s for s in snapshots["snapshots"] if s["snapshot_key"] == "t3_notepad32")
    overlay = {"host_arch": "aarch64"}
    arch_profile = "9c96be17-46eb-46d7-ba0b-9c404f97bf80"

    run4 = _shadow_session(
        session_id=f"pilot004-dry-run-04-{uuid.uuid4()}",
        exe_path=str(Path(t2["path"]) / t2["target_executable_path"]),
        wine_prefix=str(PILOT_ROOT / "dry-run/run-04-host-overlay-t2"),
        host_overlay=overlay,
    )
    run5_exe = Path(t32["path"]) / t32["target_executable_path"]
    run5 = _shadow_session(
        session_id=f"pilot004-dry-run-05-{uuid.uuid4()}",
        exe_path=str(run5_exe),
        wine_prefix=str(PILOT_ROOT / "dry-run/run-05-host-overlay-t32"),
        executable_hash=T32_HASH,
        host_overlay=overlay,
    )

    def _check(run: Dict[str, Any], run_number: int, profile_id: str) -> Dict[str, Any]:
        canonical = next((c for c in run["candidates"] if c["profile_id"] == profile_id), None)
        reasons = (canonical or {}).get("rejection_reason_codes", [])
        return {
            "run_number": run_number,
            "real_host_payload": run["real_host_payload"],
            "overlay_payload": run["overlay_payload"],
            "effective_host_payload": run["effective_host_payload"],
            "selected_profile_id": run["selected_profile_id"],
            "canonical_rejection_reason_codes": reasons,
            "host_arch_mismatch_present": "HOST_ARCH_MISMATCH" in reasons,
            "normal_execution_host_unchanged": run["real_host_payload"].get("host_arch") == "x86_64",
        }

    checks = [_check(run4, 4, CANONICAL_T2), _check(run5, 5, arch_profile)]
    report = {
        "pre_plan_overlay": True,
        "runs": checks,
        "passed": all(
            c["host_arch_mismatch_present"]
            and c["selected_profile_id"] is None
            and c["normal_execution_host_unchanged"]
            for c in checks
        ),
    }
    out = EVIDENCE / "host-overlay-audit.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True))
    return report


def update_campaign_manifest(
    *,
    snapshots: Dict[str, Any],
    setup_report: Dict[str, Any],
    run_j: Dict[str, Any],
) -> None:
    campaign_path = REPO / "data/validation/campaigns/shadow-validation-pilot-004.json"
    campaign = json.loads(campaign_path.read_text())
    snap_index = {s["snapshot_key"]: s for s in snapshots["snapshots"]}
    c2 = setup_report["candidate2"]

    campaign["status"] = "ready_for_execution_approval"
    campaign["corrective_commit_sha"] = CORRECTIVE_SHA
    campaign["promotion_eligible"] = False
    campaign["run_j_precondition"]["candidates"][1] =       {
        "profile_id": c2["profile_id"],
        "setup_id": "SETUP-T2-B-alt-manifest",
        "bridge_manifest_hash": c2["bridge_manifest_hash"],
        "executable_hash": c2["executable_hash"],
        "trust_state": c2["trust_state"],
        "lifecycle_state": "VERIFIED",
      }
    campaign["source_snapshots"] = {
        key: {
            "path": snap_index[key]["path"],
            "aggregate_sha256": snap_index[key]["aggregate_sha256"],
            **({"installed_components": snap_index[key]["installed_components"]} if key == "t2_notepad64_corefonts" else {}),
        }
        for key in ("t2_notepad64", "t2_notepad64_corefonts", "t3_notepad32")
    }
    campaign["eligibility_audit"] = "data/validation/campaigns/pilot-004-eligibility-audit.json"
    campaign["source_snapshot_registry"] = "data/validation/campaigns/pilot-004-source-snapshots.json"
    campaign_path.write_text(json.dumps(campaign, indent=2, sort_keys=True) + "\n")


def freeze_db_and_hashes() -> Dict[str, Any]:
    ts = _now()
    backup = REPO / f"data/outcomes.db.pilot-004-freeze-{ts}.bak"
    shutil.copy2(DB_PATH, backup)
    live_hash = _sha256_file(DB_PATH)
    backup_hash = _sha256_file(backup)

    def file_hash(rel: str) -> str:
        p = REPO / rel
        return _sha256_file(p) if p.exists() else None

    snap_registry = json.loads(
        (REPO / "data/validation/campaigns/pilot-004-source-snapshots.json").read_text()
    )
    snap_hashes = {s["snapshot_key"]: s["aggregate_sha256"] for s in snap_registry["snapshots"]}

    proc = subprocess.run(
        ["git", "rev-parse", "HEAD", "HEAD^{tree}"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    commit_sha, tree_sha = proc.stdout.strip().splitlines()

    record = {
        "campaign_id": "shadow-validation-pilot-004",
        "status": "ready_for_execution_approval",
        "corrective_commit_sha": CORRECTIVE_SHA,
        "freeze_commit_sha": commit_sha,
        "freeze_tree_sha": tree_sha,
        "created_at_utc": ts,
        "db_live_sha256": live_hash,
        "db_backup_path": str(backup.relative_to(REPO)),
        "db_backup_sha256": backup_hash,
        "source_snapshot_hashes": snap_hashes,
        "campaign_manifest_sha256": file_hash("data/validation/campaigns/shadow-validation-pilot-004.json"),
        "matrix_sha256": file_hash("data/validation/campaigns/pilot-004-matrix.json"),
        "commands_sha256": file_hash("data/validation/campaigns/pilot-004-commands.md"),
        "scenario_manifest_sha256": file_hash("data/validation/shadow_scenario_manifest_v1.json"),
        "eligibility_audit_sha256": file_hash("data/validation/campaigns/pilot-004-eligibility-audit.json"),
        "duplicate_metric_audit_sha256": file_hash("data/validation/evidence/pilot-004/duplicate-metric-audit.json"),
        "dry_run_windows_sha256": file_hash("data/validation/evidence/pilot-004/dry-run-windows-drift.json"),
        "dry_run_component_sha256": file_hash("data/validation/evidence/pilot-004/dry-run-component-drift.json"),
        "dry_run_known_failure_sha256": file_hash("data/validation/evidence/pilot-004/dry-run-known-failure-precondition.json"),
        "host_overlay_audit_sha256": file_hash("data/validation/evidence/pilot-004/host-overlay-audit.json"),
        "setup_t2b_sha256": file_hash("data/validation/evidence/pilot-004/setup-t2b-alt-manifest.json"),
        "run_j_audit_sha256": file_hash("data/validation/evidence/pilot-004/run-j-eligibility-ranking-audit.json"),
    }
    out = EVIDENCE / "freeze-input-hashes.json"
    out.write_text(json.dumps(record, indent=2, sort_keys=True))
    return record


STEPS = [
    "setup-t2b",
    "run-j-audit",
    "duplicate-audit",
    "snapshots",
    "windows-drift",
    "component-drift",
    "known-failure",
    "host-overlay",
    "update-manifest",
    "freeze-hashes",
    "all",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=STEPS)
    parser.add_argument("--candidate2", default=CANDIDATE2_T2)
    parser.add_argument("--force-setup", action="store_true")
    args = parser.parse_args()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    _apply_env()
    _init_shadow()

    steps = (
        ["setup-t2b", "run-j-audit", "duplicate-audit", "snapshots", "windows-drift", "component-drift", "known-failure", "host-overlay", "update-manifest"]
        if args.step == "all"
        else [args.step]
    )

    setup_report: Optional[Dict[str, Any]] = None
    snapshots: Optional[Dict[str, Any]] = None
    run_j: Optional[Dict[str, Any]] = None

    for step in steps:
        if step == "setup-t2b":
            setup_report = setup_t2b_alt_manifest(force=args.force_setup)
            print(json.dumps({"candidate2": setup_report["candidate2"]["profile_id"], "delta": setup_report["manifest_delta"]}, indent=2))
        elif step == "run-j-audit":
            run_j = run_j_audit(args.candidate2)
            print(json.dumps(run_j, indent=2))
        elif step == "duplicate-audit":
            print(json.dumps(duplicate_metric_audit(), indent=2))
        elif step == "snapshots":
            snapshots = capture_source_snapshots()
            print(json.dumps({"snapshots": [s["snapshot_key"] for s in snapshots["snapshots"]]}, indent=2))
        elif step in ("windows-drift", "component-drift", "known-failure", "host-overlay"):
            if snapshots is None:
                latest = EVIDENCE / "source-snapshots-latest.json"
                if not latest.exists():
                    raise SystemExit("snapshots step required first")
                snapshots = json.loads(latest.read_text())
            if step == "windows-drift":
                print(json.dumps(windows_drift_dry_run(snapshots), indent=2))
            elif step == "component-drift":
                print(json.dumps(component_drift_dry_run(snapshots), indent=2))
            elif step == "known-failure":
                print(json.dumps(known_failure_dry_run(snapshots), indent=2))
            else:
                print(json.dumps(host_overlay_audit(snapshots), indent=2))
        elif step == "update-manifest":
            if setup_report is None:
                setup_report = json.loads((EVIDENCE / "setup-t2b-alt-manifest.json").read_text())
            if snapshots is None:
                snapshots = json.loads((REPO / "data/validation/campaigns/pilot-004-source-snapshots.json").read_text())
            if run_j is None:
                run_j = json.loads((REPO / "data/validation/campaigns/pilot-004-eligibility-audit.json").read_text())
            update_campaign_manifest(snapshots=snapshots, setup_report=setup_report, run_j=run_j)
            print("updated shadow-validation-pilot-004.json")
        elif step == "freeze-hashes":
            print(json.dumps(freeze_db_and_hashes(), indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
