from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from alma_bridge.compatibility.profile_shadow_validation_labels import (
    TRUST_CATEGORIES,
    VALID_LABEL_TYPES,
    ValidationLabelType,
    is_trust_category_value,
)
from alma_bridge.compatibility.profile_shadow_validation_models import SCENARIO_CATEGORIES


@dataclass
class SemanticValidationIssue:
    code: str
    message: str
    severity: str = "error"
    run_number: Optional[int] = None


@dataclass
class ResolvedScenarioPlan:
    run_number: int
    scenario_id: str
    target_id: str
    disposable_env: str
    source_snapshot: Optional[str]
    drift_dimension: Optional[str]
    drift_mutation: Optional[str]
    host_overlay: Optional[Dict[str, Any]]
    expected_labels: List[str]
    expected_reason_codes: List[str]
    known_failure_fault: Optional[str]
    notes: str = ""


@dataclass
class SemanticValidationResult:
    campaign_id: str
    passed: bool
    issues: List[SemanticValidationIssue] = field(default_factory=list)
    resolved_plan: List[ResolvedScenarioPlan] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "passed": self.passed,
            "issues": [
                {
                    "code": i.code,
                    "message": i.message,
                    "severity": i.severity,
                    "run_number": i.run_number,
                }
                for i in self.issues
            ],
            "resolved_plan": [
                {
                    "run_number": p.run_number,
                    "scenario_id": p.scenario_id,
                    "target_id": p.target_id,
                    "disposable_env": p.disposable_env,
                    "source_snapshot": p.source_snapshot,
                    "drift_dimension": p.drift_dimension,
                    "drift_mutation": p.drift_mutation,
                    "host_overlay": p.host_overlay,
                    "expected_labels": p.expected_labels,
                    "expected_reason_codes": p.expected_reason_codes,
                    "known_failure_fault": p.known_failure_fault,
                    "notes": p.notes,
                }
                for p in self.resolved_plan
            ],
        }


_LABEL_ARG_RE = re.compile(r"--label-type\s+([^\s\\]+)")
_ADD_LABEL_RE = re.compile(r"add-label\b")


def _issue(
    result: SemanticValidationResult,
    code: str,
    message: str,
    *,
    severity: str = "error",
    run_number: Optional[int] = None,
) -> None:
    result.issues.append(
        SemanticValidationIssue(code=code, message=message, severity=severity, run_number=run_number)
    )
    if severity == "error":
        result.passed = False


def validate_commands_labels(commands_text: str, result: SemanticValidationResult) -> None:
    for match in _LABEL_ARG_RE.finditer(commands_text):
        label = match.group(1).strip().strip("'\"")
        if is_trust_category_value(label):
            _issue(
                result,
                "INVALID_LABEL_TYPE_TRUST_CATEGORY",
                f"Commands document uses trust category {label!r} as label_type",
            )
        elif label not in VALID_LABEL_TYPES:
            _issue(
                result,
                "INVALID_LABEL_TYPE",
                f"Commands document uses unknown label_type {label!r}",
            )


def validate_scenario_label_rubric(
    run: Mapping[str, Any],
    result: SemanticValidationResult,
) -> None:
    run_no = int(run["run_number"])
    scenario_id = str(run["scenario_id"])
    labels = list(run.get("expected_labels") or [])
    rubric = run.get("label_rubric") or {}

    for label in labels:
        if is_trust_category_value(label):
            _issue(
                result,
                "TRUST_CATEGORY_AS_LABEL",
                f"Run {run_no}: expected_labels contains trust category {label!r}",
                run_number=run_no,
            )
        elif label not in VALID_LABEL_TYPES:
            _issue(
                result,
                "INVALID_LABEL_TYPE",
                f"Run {run_no}: invalid expected label {label!r}",
                run_number=run_no,
            )

    if scenario_id == "I_trust_state_imported":
        expected = rubric.get("imported_fixture_label") or ValidationLabelType.REJECTED_CORRECT.value
        if expected != ValidationLabelType.REJECTED_CORRECT.value:
            _issue(
                result,
                "IMPORTED_TRUST_LABEL_RUBRIC",
                f"Run {run_no}: imported trust must use rejected_correct, got {expected!r}",
                run_number=run_no,
            )
        if "shadow_observation_only" in labels:
            _issue(
                result,
                "PILOT003_DEFECT_LABEL",
                f"Run {run_no}: reproduces Pilot-003 invalid label shadow_observation_only",
                run_number=run_no,
            )


def validate_drift_commands(run: Mapping[str, Any], result: SemanticValidationResult) -> None:
    run_no = int(run["run_number"])
    scenario_id = str(run["scenario_id"])
    drift = run.get("drift_induction") or {}
    shadow = run.get("shadow_scenario_inputs") or {}

    if scenario_id == "E_prefix_drift_windows":
        declared = drift.get("dimension") or "windows_version"
        if declared != "windows_version":
            _issue(
                result,
                "DRIFT_DIMENSION_MISMATCH",
                f"Run {run_no}: E_prefix_drift_windows must declare windows_version drift",
                run_number=run_no,
            )
        target_ver = drift.get("mutate_to") or drift.get("windows_version")
        if not target_ver:
            _issue(
                result,
                "WINDOWS_DRIFT_TARGET_MISSING",
                f"Run {run_no}: windows drift must declare mutate_to version",
                run_number=run_no,
            )
        if drift.get("command") and "corefonts" in str(drift.get("command")):
            _issue(
                result,
                "PILOT003_DEFECT_DRIFT",
                f"Run {run_no}: windows drift must not add components (Pilot-003 Run 7 defect)",
                run_number=run_no,
            )

    if scenario_id == "E_prefix_drift_component":
        declared = drift.get("dimension") or "installed_components"
        if declared != "installed_components":
            _issue(
                result,
                "DRIFT_DIMENSION_MISMATCH",
                f"Run {run_no}: E_prefix_drift_component must declare installed_components drift",
                run_number=run_no,
            )
        component = drift.get("remove_component") or drift.get("component")
        if not component:
            _issue(
                result,
                "COMPONENT_DRIFT_TARGET_MISSING",
                f"Run {run_no}: component drift must declare remove_component",
                run_number=run_no,
            )
        if drift.get("command") and "winetricks -q corefonts" in str(drift.get("command")):
            _issue(
                result,
                "PILOT003_DEFECT_DRIFT",
                f"Run {run_no}: component drift must remove, not add corefonts",
                run_number=run_no,
            )

    if scenario_id == "D_incompatible_host_drift":
        overlay = shadow.get("host_payload_overlay") or {}
        if not overlay:
            _issue(
                result,
                "HOST_OVERLAY_MISSING",
                f"Run {run_no}: D_incompatible_host_drift requires host_payload_overlay",
                run_number=run_no,
            )
        if shadow.get("evaluation_mode") == "shadow_read_only_host_class_mismatch":
            _issue(
                result,
                "POST_HOC_OVERLAY_FORBIDDEN",
                f"Run {run_no}: post-hoc overlay evaluation_mode is not accepted (Pilot-003 defect)",
                run_number=run_no,
            )
        if not shadow.get("pre_plan_overlay"):
            _issue(
                result,
                "PRE_PLAN_OVERLAY_REQUIRED",
                f"Run {run_no}: host overlay must be applied before create_prediction (pre_plan_overlay)",
                run_number=run_no,
            )


def validate_known_failure(run: Mapping[str, Any], result: SemanticValidationResult) -> None:
    run_no = int(run["run_number"])
    if str(run.get("scenario_id")) != "G_known_compatibility_failure":
        return
    fault = run.get("known_failure") or {}
    if not fault.get("induced_fault"):
        _issue(
            result,
            "KNOWN_FAILURE_FAULT_MISSING",
            f"Run {run_no}: G scenario must declare induced_fault",
            run_number=run_no,
        )
    if fault.get("expects_bridge_success"):
        _issue(
            result,
            "KNOWN_FAILURE_EXPECTS_SUCCESS",
            f"Run {run_no}: known failure scenario must not expect bridge success",
            run_number=run_no,
        )


def validate_run_j_provenance(
    campaign_manifest: Mapping[str, Any],
    result: SemanticValidationResult,
) -> None:
    run_j = campaign_manifest.get("run_j_precondition") or {}
    candidates = run_j.get("candidates") or []
    if len(candidates) < 2:
        _issue(
            result,
            "RUN_J_CANDIDATES_MISSING",
            "Run J requires at least two documented candidate provenance entries before freeze",
        )
        return
    manifests = {str(c.get("bridge_manifest_hash") or "") for c in candidates}
    if len(manifests) < 2:
        _issue(result, "RUN_J_DISTINCT_MANIFESTS", "Run J candidates must have distinct bridge_manifest_hash")
    for cand in candidates:
        source = str(cand.get("source_session_id") or cand.get("setup_id") or "")
        if source in {"", "audit-wine-gui"}:
            _issue(
                result,
                "RUN_J_PROVENANCE_INVALID",
                f"Run J candidate {cand.get('profile_id')} has invalid source {source!r} (Pilot-003 defect)",
            )
        elif not (source.startswith("SETUP-") or source.startswith("shadow-validation-pilot")):
            _issue(
                result,
                "RUN_J_PROVENANCE_INVALID",
                f"Run J candidate {cand.get('profile_id')} source must be SETUP-* or campaign session, got {source!r}",
            )
        if cand.get("legacy") or cand.get("imported"):
            _issue(
                result,
                "RUN_J_CANDIDATE_INELIGIBLE",
                f"Run J candidate {cand.get('profile_id')} is excluded class",
            )


def validate_execution_targets(
    campaign_manifest: Mapping[str, Any],
    matrix_runs: Sequence[Mapping[str, Any]],
    result: SemanticValidationResult,
) -> None:
    snap_guard = str(
        (campaign_manifest.get("target_paths") or {}).get("source_snapshot_guard_root") or ""
    ).replace("~", "")
    for run in matrix_runs:
        run_no = int(run["run_number"])
        env = str(run.get("disposable_env") or "")
        if "snapshots/" in env and not env.startswith("runs/"):
            _issue(
                result,
                "SNAPSHOT_EXECUTION_TARGET",
                f"Run {run_no}: disposable_env must not execute against snapshots/",
                run_number=run_no,
            )
        if snap_guard and env.startswith("snapshots"):
            _issue(
                result,
                "SNAPSHOT_EXECUTION_TARGET",
                f"Run {run_no}: must clone to runs/, not snapshots/",
                run_number=run_no,
            )


def build_resolved_plan(
    matrix_runs: Sequence[Mapping[str, Any]],
) -> List[ResolvedScenarioPlan]:
    plans: List[ResolvedScenarioPlan] = []
    for run in sorted(matrix_runs, key=lambda r: int(r["run_number"])):
        shadow = run.get("shadow_scenario_inputs") or {}
        drift = run.get("drift_induction") or {}
        fault = run.get("known_failure") or {}
        plans.append(
            ResolvedScenarioPlan(
                run_number=int(run["run_number"]),
                scenario_id=str(run["scenario_id"]),
                target_id=str(run.get("target_id") or ""),
                disposable_env=str(run.get("disposable_env") or ""),
                source_snapshot=run.get("source_snapshot"),
                drift_dimension=drift.get("dimension"),
                drift_mutation=drift.get("mutate_to") or drift.get("remove_component"),
                host_overlay=shadow.get("host_payload_overlay"),
                expected_labels=list(run.get("expected_labels") or []),
                expected_reason_codes=list(shadow.get("expected_rejection_reasons") or []),
                known_failure_fault=fault.get("induced_fault"),
                notes=str(run.get("notes") or ""),
            )
        )
    return plans


def validate_campaign_semantics(
    *,
    campaign_manifest: Mapping[str, Any],
    matrix_runs: Sequence[Mapping[str, Any]],
    repo_root: Path,
) -> SemanticValidationResult:
    campaign_id = str(campaign_manifest.get("campaign_id") or "unknown")
    result = SemanticValidationResult(campaign_id=campaign_id, passed=True)

    commands_doc = campaign_manifest.get("execution_commands")
    if commands_doc:
        cmd_path = repo_root / str(commands_doc)
        if cmd_path.exists():
            validate_commands_labels(cmd_path.read_text(encoding="utf-8"), result)

    for run in matrix_runs:
        scenario_id = str(run.get("scenario_id") or "")
        if scenario_id and scenario_id not in SCENARIO_CATEGORIES and not scenario_id.startswith("E_prefix_drift"):
            pass  # manifest-level check handles unknown ids
        validate_scenario_label_rubric(run, result)
        validate_drift_commands(run, result)
        validate_known_failure(run, result)

    validate_run_j_provenance(campaign_manifest, result)
    validate_execution_targets(campaign_manifest, matrix_runs, result)

    flags = campaign_manifest.get("feature_flags") or {}
    if flags.get("ALMA_BRIDGE_COMPATIBILITY_PROFILE_REUSE_ENABLED"):
        _issue(result, "ACTIVE_REUSE_ENABLED", "Active reuse must remain disabled")

    result.resolved_plan = build_resolved_plan(matrix_runs)
    return result
