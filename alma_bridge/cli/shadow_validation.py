from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from alma_bridge.compatibility.profile_shadow_validation_analyzer import ShadowFailureAnalyzer
from alma_bridge.compatibility.profile_shadow_validation_export import write_export_file
from alma_bridge.compatibility.profile_shadow_validation_models import ShadowLabelInput
from alma_bridge.compatibility.profile_shadow_validation_reporter import ShadowValidationReporter
from alma_bridge.compatibility.profile_shadow_validation_store import (
    add_label,
    init_validation_store,
    register_validation_run,
    sync_scenario_manifest,
)
from alma_bridge.storage.outcomes import init_outcome_store
from alma_bridge.validation.campaign_freeze_validator import validate_campaign_matrix


def _cmd_report(_args: argparse.Namespace) -> int:
    report = ShadowValidationReporter.generate_report()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _cmd_gates(_args: argparse.Namespace) -> int:
    report = ShadowValidationReporter.generate_report()
    gates = report.get("promotion_gates", {})
    print(json.dumps(gates, indent=2, sort_keys=True))
    ready = gates.get("promotion_ready", False)
    print(f"\nPromotion ready: {ready}", file=sys.stderr)
    print(gates.get("recommendation", ""), file=sys.stderr)
    return 0 if ready else 1


def _cmd_sync_manifest(_args: argparse.Namespace) -> int:
    count = sync_scenario_manifest()
    print(json.dumps({"scenarios_synced": count}))
    return 0


def _cmd_register_run(args: argparse.Namespace) -> int:
    run_id = register_validation_run(
        session_id=args.session_id,
        scenario_id=args.scenario_id,
        program_kind=args.program_kind,
        application_family=args.application_family,
    )
    print(json.dumps({"validation_run_id": run_id}))
    return 0


def _cmd_add_label(args: argparse.Namespace) -> int:
    label_id = add_label(
        ShadowLabelInput(
            shadow_event_id=args.shadow_event_id,
            label_type=args.label_type,
            label_source=args.source,
            reviewer=args.reviewer,
            reason=args.reason,
            profile_id=args.profile_id,
            evidence_refs=args.evidence.split(",") if args.evidence else [],
        )
    )
    print(json.dumps({"label_id": label_id}))
    return 0


def _cmd_analyze_failures(_args: argparse.Namespace) -> int:
    recorded = ShadowFailureAnalyzer.analyze_and_record()
    print(json.dumps({"recorded": len(recorded), "analysis_ids": recorded}))
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    path = write_export_file(
        Path(args.output),
        shadow_event_id=args.shadow_event_id,
        session_id=args.session_id,
    )
    print(json.dumps({"export_path": str(path)}))
    return 0


def _cmd_validate_freeze(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    campaign_path = Path(args.campaign_manifest)
    if not campaign_path.is_absolute():
        campaign_path = repo_root / campaign_path
    matrix_path = Path(args.matrix)
    if not matrix_path.is_absolute():
        matrix_path = repo_root / matrix_path
    scenario_manifest_path = Path(args.scenario_manifest)
    if not scenario_manifest_path.is_absolute():
        scenario_manifest_path = repo_root / scenario_manifest_path

    campaign_manifest = json.loads(campaign_path.read_text(encoding="utf-8"))
    matrix_doc = json.loads(matrix_path.read_text(encoding="utf-8"))
    runs = matrix_doc.get("runs") or matrix_doc
    evidence_dir = None
    if args.evidence_dir:
        evidence_dir = Path(args.evidence_dir)
        if not evidence_dir.is_absolute():
            evidence_dir = repo_root / evidence_dir

    result = validate_campaign_matrix(
        campaign_manifest=campaign_manifest,
        matrix_runs=runs,
        scenario_manifest_path=scenario_manifest_path,
        repo_root=repo_root,
        evidence_dir=evidence_dir,
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if not result.passed:
        print("\nCampaign NOT ready for execution approval.", file=sys.stderr)
        return 1
    print("\nCampaign ready for execution approval.", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="alma-bridge-shadow-validation",
        description="Read-only shadow validation reporting and labeling tools.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("report", help="Full shadow validation report (read-only)").set_defaults(
        func=_cmd_report
    )
    sub.add_parser("gates", help="Promotion gate status only (read-only)").set_defaults(
        func=_cmd_gates
    )
    sub.add_parser("sync-manifest", help="Sync scenario manifest into SQLite").set_defaults(
        func=_cmd_sync_manifest
    )

    reg = sub.add_parser("register-run", help="Link session to validation scenario")
    reg.add_argument("--session-id", required=True)
    reg.add_argument("--scenario-id", required=True)
    reg.add_argument("--program-kind", default=None)
    reg.add_argument("--application-family", default=None)
    reg.set_defaults(func=_cmd_register_run)

    label = sub.add_parser("add-label", help="Add operator label (append-only)")
    label.add_argument("--shadow-event-id", required=True)
    label.add_argument("--label-type", required=True)
    label.add_argument("--source", default="operator")
    label.add_argument("--reviewer", required=True)
    label.add_argument("--reason", required=True)
    label.add_argument("--profile-id", default=None)
    label.add_argument("--evidence", default="")
    label.set_defaults(func=_cmd_add_label)

    sub.add_parser("analyze-failures", help="Record failure analyses from comparisons").set_defaults(
        func=_cmd_analyze_failures
    )

    exp = sub.add_parser("export", help="Sanitized export bundle")
    exp.add_argument("--output", required=True)
    exp.add_argument("--shadow-event-id", default=None)
    exp.add_argument("--session-id", default=None)
    exp.set_defaults(func=_cmd_export)

    vf = sub.add_parser(
        "validate-freeze",
        help="Read-only pre-freeze campaign validator (blocks ready_for_execution_approval on mismatch)",
    )
    vf.add_argument(
        "--campaign-manifest",
        default="data/validation/campaigns/shadow-validation-pilot-004.json",
    )
    vf.add_argument("--matrix", default="data/validation/campaigns/pilot-004-matrix.json")
    vf.add_argument(
        "--scenario-manifest",
        default="data/validation/shadow_scenario_manifest_v1.json",
    )
    vf.add_argument("--evidence-dir", default="data/validation/evidence/pilot-004")
    vf.set_defaults(func=_cmd_validate_freeze)

    args = parser.parse_args(argv)
    init_outcome_store()
    init_validation_store()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
