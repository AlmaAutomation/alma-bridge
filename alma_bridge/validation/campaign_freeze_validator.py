from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence


@dataclass
class CampaignValidationIssue:
    code: str
    message: str
    severity: str = "error"


@dataclass
class CampaignValidationResult:
    campaign_id: str
    passed: bool
    issues: List[CampaignValidationIssue] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "passed": self.passed,
            "issues": [
                {"code": i.code, "message": i.message, "severity": i.severity}
                for i in self.issues
            ],
        }


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _tree_hash(prefix: Path) -> Optional[str]:
    if not prefix.exists():
        return None
    digest = hashlib.sha256()
    for path in sorted(prefix.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(prefix)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def validate_campaign_matrix(
    *,
    campaign_manifest: Mapping[str, Any],
    matrix_runs: Sequence[Mapping[str, Any]],
    scenario_manifest_path: Path,
    repo_root: Path,
    evidence_dir: Optional[Path] = None,
) -> CampaignValidationResult:
    """
    Read-only pre-freeze validator. Refuses ready_for_execution_approval on mismatch.
    """
    campaign_id = str(campaign_manifest.get("campaign_id") or "unknown")
    result = CampaignValidationResult(campaign_id=campaign_id, passed=True)

    def issue(code: str, message: str, severity: str = "error") -> None:
        result.issues.append(CampaignValidationIssue(code=code, message=message, severity=severity))
        if severity == "error":
            result.passed = False

    scenario_manifest = _load_json(scenario_manifest_path)
    manifest_ids = {
        str(s["scenario_id"])
        for s in scenario_manifest.get("scenarios", [])
        if s.get("scenario_id")
    }
    manifest_categories = {
        str(s.get("scenario_category") or s["scenario_id"]): str(s["scenario_id"])
        for s in scenario_manifest.get("scenarios", [])
    }

    run_numbers: List[int] = []
    for run in matrix_runs:
        run_no = int(run["run_number"])
        if run_no in run_numbers:
            issue("DUPLICATE_RUN_NUMBER", f"Duplicate run number: {run_no}")
        run_numbers.append(run_no)

        scenario_id = str(run["scenario_id"])
        scenario_category = str(run.get("scenario_category") or "")

        if scenario_id not in manifest_ids:
            issue(
                "SCENARIO_ID_MANIFEST_MISMATCH",
                f"Run {run_no}: scenario_id '{scenario_id}' absent from scenario manifest",
            )
        if scenario_category and scenario_category != scenario_id:
            if scenario_category not in manifest_categories and scenario_category not in manifest_ids:
                issue(
                    "SCENARIO_CATEGORY_CONFLICT",
                    f"Run {run_no}: category '{scenario_category}' is not a registered manifest id",
                )
            if scenario_id in manifest_ids and scenario_category != scenario_id:
                category_for_id = next(
                    (
                        str(s.get("scenario_category"))
                        for s in scenario_manifest.get("scenarios", [])
                        if str(s.get("scenario_id")) == scenario_id
                    ),
                    None,
                )
                if category_for_id and category_for_id == scenario_id:
                    issue(
                        "SCENARIO_CATEGORY_ID_CONFLICT",
                        f"Run {run_no}: scenario_id equals category but differs from manifest category",
                    )

        for req in ("target_id", "program_kind", "application_family", "disposable_env"):
            if not run.get(req):
                issue("MISSING_SCENARIO_METADATA", f"Run {run_no}: missing {req}")

    flags = campaign_manifest.get("feature_flags") or {}
    if flags.get("ALMA_BRIDGE_COMPATIBILITY_PROFILE_REUSE_ENABLED"):
        issue("ACTIVE_REUSE_ENABLED", "ALMA_BRIDGE_COMPATIBILITY_PROFILE_REUSE_ENABLED must be false")
    if not flags.get("ALMA_BRIDGE_VALIDATION_CAMPAIGN_MODE"):
        issue("CAMPAIGN_MODE_DISABLED", "ALMA_BRIDGE_VALIDATION_CAMPAIGN_MODE must be true")

    exclusion = campaign_manifest.get("legacy_profile_exclusion") or {}
    if not exclusion.get("excluded_profile_ids"):
        issue("LEGACY_EXCLUSION_MISSING", "legacy_profile_exclusion.excluded_profile_ids required")

    targets = campaign_manifest.get("target_programs") or []
    for target in targets:
        canonical = target.get("canonical_path") or ""
        if canonical.startswith("scripts/"):
            path = repo_root / canonical
            if not path.exists():
                issue("TARGET_MISSING", f"Target path missing: {canonical}")

    snapshots = campaign_manifest.get("source_snapshots") or {}
    for key, snap in snapshots.items():
        snap_path = Path(str(snap.get("path", ""))).expanduser()
        expected = snap.get("aggregate_sha256")
        if not snap_path.exists():
            issue("SOURCE_SNAPSHOT_MISSING", f"Source snapshot missing: {key} -> {snap_path}")
            continue
        if not expected:
            continue
        actual = _tree_hash(snap_path)
        if actual != expected:
            issue(
                "SOURCE_SNAPSHOT_HASH_MISMATCH",
                f"Source snapshot hash mismatch for {key}: expected {expected}, got {actual}",
            )

    primary = str((campaign_manifest.get("target_paths") or {}).get("ascension_primary_prefix") or "")
    if primary and "guard_reference" not in primary and "not_execution" not in primary:
        issue("PRIMARY_PREFIX_REFERENCE", "Primary prefix must be guard-only reference")

    if evidence_dir is not None:
        if not evidence_dir.exists():
            issue("EVIDENCE_DIR_MISSING", f"Evidence directory missing: {evidence_dir}")
        elif not os.access(evidence_dir, os.W_OK):
            issue("EVIDENCE_DIR_NOT_WRITABLE", f"Evidence directory not writable: {evidence_dir}")

    commands_doc = campaign_manifest.get("execution_commands")
    if commands_doc:
        cmd_path = repo_root / str(commands_doc)
        if not cmd_path.exists():
            issue("COMMANDS_DOC_MISSING", f"Execution commands document missing: {commands_doc}")
        else:
            for run in matrix_runs:
                token = f"run-{int(run['run_number']):02d}"
                if token not in cmd_path.read_text(encoding="utf-8"):
                    issue(
                        "COMMANDS_DOC_RUN_MISSING",
                        f"Commands document missing reference for run {run['run_number']} ({token})",
                    )

    run_j = campaign_manifest.get("run_j_precondition") or {}
    if run_j.get("blocked_if_unmet") and run_j.get("status") == "blocked":
        issue(
            "RUN_J_PRECONDITION_BLOCKED",
            "Run J precondition unmet; matrix must mark run 13 blocked",
            severity="warning",
        )

    return result


def validate_pilot002_mismatch_would_fail(matrix_runs: Sequence[Mapping[str, Any]], scenario_ids: set[str]) -> bool:
    """Return True if Pilot-002 style E_prefix_drift id would be caught."""
    for run in matrix_runs:
        if str(run.get("scenario_id")) == "E_prefix_drift" and "E_prefix_drift" not in scenario_ids:
            return True
    return False
