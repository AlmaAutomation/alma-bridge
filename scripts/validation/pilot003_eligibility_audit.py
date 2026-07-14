#!/usr/bin/env python3
"""Read-only Pilot-003 freeze eligibility audit — persists evidence, no mutations."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from alma_bridge.compatibility.expected_verification_contract import (
    expected_verification_contract_for_kind,
)
from alma_bridge.compatibility.profile_host_class import (
    build_host_compatibility_class_id,
    build_host_compatibility_class_payload,
)
from alma_bridge.compatibility.profile_shadow_eligibility import evaluate_candidate_eligibility
from alma_bridge.compatibility.profile_store import load_profile_bundle
from alma_bridge.storage.outcomes import init_outcome_store
from tests.pe_test_helpers import write_minimal_pe
from alma_bridge.compatibility.program_kind import IMAGE_SUBSYSTEM_WINDOWS_GUI
from alma_bridge.compatibility.profile_lineage import promote_candidate_snapshot
from tests.profile_test_helpers import (
    build_test_snapshot,
    sample_hardware,
    sample_verification_payload,
    sample_wine_gui_verification_payload,
)

CANONICAL_T2 = "a5576257-65b5-485f-a966-8273bccd8146"
CANONICAL_T3 = "281e69a0-e3e8-46cc-8de5-2639facce95f"
T2_HASH = "108168df2b9679c5ef4004a5fa63990c99b189661ee3cac4bb8f9dd467ad6d69"
T3_HASH = "a2bddbb8d43eb96b750813ab8f30db847d2b60d2838dd5fcb36348a719157266"
NOTEPAD32_HASH = "503665cbf1e3be907387c2b76beb25bcdef7d326738adf6f06ff53b9984a2684"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _eval_case(
    *,
    name: str,
    bundle: Mapping[str, Any],
    program_identity_key: str,
    host_payload: Mapping[str, Any],
    expected_kind: str,
    required_capabilities: Optional[List[str]] = None,
) -> Dict[str, Any]:
    expected = expected_verification_contract_for_kind({"program_kind": expected_kind})
    evaluation = evaluate_candidate_eligibility(
        profile_bundle=bundle,
        program_identity_key=program_identity_key,
        host_compatibility_class_id=build_host_compatibility_class_id(host_payload),
        host_payload=host_payload,
        expected_verification=expected,
        required_capabilities=required_capabilities,
    )
    return {
        "case": name,
        "profile_id": bundle["profile"]["profile_id"],
        "eligibility_status": evaluation.eligibility_status,
        "rejection_reason_codes": evaluation.rejection_reason_codes,
        "winner_selectable": evaluation.winner_selectable,
        "verification_binding_compatible": evaluation.verification_binding_compatible,
    }


def _profile_host_payload(bundle: Mapping[str, Any]) -> Dict[str, Any]:
    return json.loads(bundle["host"]["host_class_json"])


def _electron_bundle(tmp: Path):
    app_dir = tmp / "ElectronApp"
    app_dir.mkdir(exist_ok=True)
    exe2 = app_dir / "ElectronApp.exe"
    write_minimal_pe(exe2, subsystem=IMAGE_SUBSYSTEM_WINDOWS_GUI)
    for name in ("resources.pak", "snapshot_blob.bin", "v8_context_snapshot.bin"):
        (app_dir / name).write_bytes(b"x")
    snap = build_test_snapshot(
        session_id="electron-audit",
        file_path=str(exe2),
        executable_hash="electronhash0001",
        verification_payload=sample_verification_payload(),
        phase="launcher",
    )
    profile_id, _ = promote_candidate_snapshot(snap)
    bundle = load_profile_bundle(profile_id)
    assert bundle is not None
    return bundle


def main() -> int:
    os.environ.setdefault("ALMA_BRIDGE_DB_PATH", str(REPO / "data/outcomes.db"))
    init_outcome_store()

    tmp = REPO / "data/validation/evidence/pilot-003/.audit-tmp"
    tmp.mkdir(parents=True, exist_ok=True)

    t2 = load_profile_bundle(CANONICAL_T2)
    t3 = load_profile_bundle(CANONICAL_T3)
    assert t2 and t3

    base_host = _profile_host_payload(t2)
    incompatible_host = dict(base_host)
    incompatible_host["host_arch"] = "aarch64"

    cases: List[Dict[str, Any]] = []

    cases.append(
        _eval_case(
            name="T2_profile_on_T2_wine_gui_target",
            bundle=t2,
            program_identity_key=t2["program"]["program_identity_key"],
            host_payload=base_host,
            expected_kind="pe_windows_gui",
        )
    )
    cases.append(
        _eval_case(
            name="T3_profile_on_T3_wine_gui_target",
            bundle=t3,
            program_identity_key=t3["program"]["program_identity_key"],
            host_payload=_profile_host_payload(t3),
            expected_kind="pe_windows_gui",
        )
    )
    cases.append(
        _eval_case(
            name="T2_profile_on_T3_executable",
            bundle=t2,
            program_identity_key=t3["program"]["program_identity_key"],
            host_payload=base_host,
            expected_kind="pe_windows_gui",
        )
    )

    native_snap = build_test_snapshot(verification_payload=sample_verification_payload())
    native_id, _ = promote_candidate_snapshot(native_snap)
    native = load_profile_bundle(native_id)
    assert native
    cases.append(
        _eval_case(
            name="native_profile_on_wine_gui_target",
            bundle=native,
            program_identity_key=native["program"]["program_identity_key"],
            host_payload=base_host,
            expected_kind="pe_windows_gui",
        )
    )

    electron = _electron_bundle(tmp)
    cases.append(
        _eval_case(
            name="electron_profile_on_ordinary_wine_gui_target",
            bundle=electron,
            program_identity_key=t2["program"]["program_identity_key"],
            host_payload=base_host,
            expected_kind="pe_windows_gui",
        )
    )

    cases.append(
        _eval_case(
            name="run4_T2_candidate_host_arch_mismatch",
            bundle=t2,
            program_identity_key=t2["program"]["program_identity_key"],
            host_payload=incompatible_host,
            expected_kind="pe_windows_gui",
        )
    )

    cases.append(
        _eval_case(
            name="run4_required_capability_missing",
            bundle=t2,
            program_identity_key=t2["program"]["program_identity_key"],
            host_payload=base_host,
            expected_kind="pe_windows_gui",
            required_capabilities=["validation_scenario_gpu_cuda"],
        )
    )

    arch_profile_id = os.environ.get("PILOT003_ARCH_PROFILE_ID", "9c96be17-46eb-46d7-ba0b-9c404f97bf80")
    arch_bundle = load_profile_bundle(arch_profile_id)
    if arch_bundle:
        arch_host = _profile_host_payload(arch_bundle)
        cases.append(
            _eval_case(
                name="run5_arch_profile_present",
                bundle=arch_bundle,
                program_identity_key=arch_bundle["program"]["program_identity_key"],
                host_payload=arch_host,
                expected_kind="pe_windows_gui",
            )
        )
        cases.append(
            _eval_case(
                name="run5_arch_profile_host_arch_mismatch",
                bundle=arch_bundle,
                program_identity_key=arch_bundle["program"]["program_identity_key"],
                host_payload={**arch_host, "host_arch": "aarch64"},
                expected_kind="pe_windows_gui",
            )
        )

    # Verifier version / policy checks via direct bundle mutation
    wine_gui_snap = build_test_snapshot(
        session_id="audit-wine-gui",
        file_path=str(tmp / "gui.exe"),
        executable_hash=T2_HASH,
        strategy_id="wine_host",
        runtime="wine",
        phase="wine_gui",
        verification_payload=sample_wine_gui_verification_payload(),
    )
    write_minimal_pe(tmp / "gui.exe", subsystem=IMAGE_SUBSYSTEM_WINDOWS_GUI)
    wg_id, _ = promote_candidate_snapshot(wine_gui_snap)
    wg = load_profile_bundle(wg_id)
    assert wg
    wg_host = _profile_host_payload(wg)
    cases.append(
        _eval_case(
            name="compatible_policy_version_eligible",
            bundle=wg,
            program_identity_key=wg["program"]["program_identity_key"],
            host_payload=wg_host,
            expected_kind="pe_windows_gui",
        )
    )

    bad_binding = dict(wg)
    bad_profile = dict(wg["profile"])
    bad_profile["verification_binding_key"] = "deadbeef"
    bad_binding["profile"] = bad_profile
    cases.append(
        _eval_case(
            name="incompatible_verifier_binding_rejected",
            bundle=bad_binding,
            program_identity_key=wg["program"]["program_identity_key"],
            host_payload=wg_host,
            expected_kind="pe_windows_gui",
        )
    )

    from alma_bridge.compatibility.expected_verification_contract import ExpectedVerificationContract
    from alma_bridge.compatibility.verification_binding_compatibility import (
        evaluate_verification_binding_compatibility,
    )
    from alma_bridge.session.services.verification import WINE_GUI_POLICY_ID, WINE_GUI_POLICY_VERSION

    strict_expected = ExpectedVerificationContract(
        policy_id=WINE_GUI_POLICY_ID,
        policy_version=WINE_GUI_POLICY_VERSION,
        phase="wine_gui",
        program_kind="pe_windows_gui",
        required_checks=["process_survives", "target_process_identity", "extra_required_check"],
        optional_checks=[],
    )
    strict_result = evaluate_verification_binding_compatibility(
        profile_bundle=wg,
        expected=strict_expected,
    )
    cases.append(
        {
            "case": "missing_required_check_rejected",
            "profile_id": wg["profile"]["profile_id"],
            "eligibility_status": "rejected" if strict_result.reason_codes else "eligible",
            "rejection_reason_codes": strict_result.reason_codes,
            "winner_selectable": False,
            "verification_binding_compatible": strict_result.compatible,
        }
    )

    payload = {
        "campaign_id": "shadow-validation-pilot-003",
        "audit_at_utc": _now(),
        "corrective_commit": "6bf06ca14e760a4f976279f1ee9fd201dffa2080",
        "cases": cases,
        "run4_expected_reason": "HOST_ARCH_MISMATCH",
        "run5_expected_reason": "HOST_ARCH_MISMATCH",
        "all_passed": all(
            [
                (cases[0]["eligibility_status"] == "eligible"),
                (cases[1]["eligibility_status"] == "eligible"),
                ("PROGRAM_IDENTITY_MISMATCH" in cases[2]["rejection_reason_codes"]),
                ("VERIFICATION_POLICY_ID_MISMATCH" in cases[3]["rejection_reason_codes"]),
                ("HOST_ARCH_MISMATCH" in next(c for c in cases if c["case"] == "run4_T2_candidate_host_arch_mismatch")["rejection_reason_codes"]),
                ("REQUIRED_CAPABILITY_MISSING" in next(c for c in cases if c["case"] == "run4_required_capability_missing")["rejection_reason_codes"]),
                ("HOST_ARCH_MISMATCH" in next(c for c in cases if c["case"] == "run5_arch_profile_host_arch_mismatch")["rejection_reason_codes"]),
                ("VERIFIER_VERSION_INCOMPATIBLE" in next(c for c in cases if c["case"] == "incompatible_verifier_binding_rejected")["rejection_reason_codes"]),
                ("REQUIRED_CHECKS_MISMATCH" in next(c for c in cases if c["case"] == "missing_required_check_rejected")["rejection_reason_codes"]),
            ]
        ),
    }

    out = REPO / "data/validation/evidence/pilot-003" / f"eligibility-audit-{_now()}.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
