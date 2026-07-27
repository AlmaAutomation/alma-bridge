from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Set

COMPARISON_SCHEMA_VERSION = "campaign_scoped_comparison_v1"

LEGACY_EXCLUDED_PROFILE_IDS: FrozenSet[str] = frozenset(
    {
        "425f8664-7ddd-4a99-b984-435051027e8f",
        "bebf5c5f-6719-4ac2-8e75-29ac6c839bf3",
        "6aec0dd2-e298-4173-aec3-603e2aae691b",
        "9b0cf7ff-aca8-44ee-b354-28505ac3c60d",
    }
)

LEGACY_EXCLUSION_REASON_CODES: FrozenSet[str] = frozenset({"WINEPREFIX_MANIFEST_IDENTITY_LEAK"})

EXCLUDED_CAMPAIGN_IDS: FrozenSet[str] = frozenset(
    {
        "shadow-validation-pilot-001",
        "shadow-validation-pilot-002",
        "shadow-validation-pilot-003",
    }
)

CONTROLLED_DUPLICATE_FIXTURE_IDS: FrozenSet[str] = frozenset(
    {"B_redundant_different_profile"}
)


@dataclass
class ValidationEvidenceScope:
    """Explicit inclusion/exclusion boundaries for promotion-gate metrics."""

    campaign_id: str
    included_shadow_event_ids: List[str] = field(default_factory=list)
    included_session_ids: List[str] = field(default_factory=list)
    included_setup_fixture_ids: List[str] = field(default_factory=list)
    excluded_campaign_ids: List[str] = field(default_factory=list)
    excluded_profile_ids: List[str] = field(default_factory=list)
    excluded_legacy_reason_codes: List[str] = field(default_factory=list)
    excluded_shadow_event_ids: List[str] = field(default_factory=list)
    excluded_setup_fixture_ids: List[str] = field(default_factory=list)
    excluded_session_ids: List[str] = field(default_factory=list)
    comparison_schema_version: str = COMPARISON_SCHEMA_VERSION
    generated_at: str = ""

    def __post_init__(self) -> None:
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def included_shadow_event_id_set(self) -> Set[str]:
        return set(self.included_shadow_event_ids)

    @property
    def included_session_id_set(self) -> Set[str]:
        return set(self.included_session_ids)

    @property
    def excluded_shadow_event_id_set(self) -> Set[str]:
        return set(self.excluded_shadow_event_ids)

    @property
    def excluded_session_id_set(self) -> Set[str]:
        return set(self.excluded_session_ids)

    @property
    def excluded_profile_id_set(self) -> Set[str]:
        return set(self.excluded_profile_ids)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_evidence_quality_review(path: Optional[Path] = None) -> Dict[str, Any]:
    review_path = path or (
        _repo_root() / "data/validation/campaigns/pilot-004-evidence-quality-review.json"
    )
    if not review_path.is_file():
        return {"runs": []}
    return json.loads(review_path.read_text(encoding="utf-8"))


def build_pilot004_evidence_scope(
    *,
    completion_report_path: Optional[Path] = None,
    quality_review_path: Optional[Path] = None,
) -> ValidationEvidenceScope:
    """Build campaign-scoped evidence boundaries for Pilot-004 promotion gates."""
    report_path = completion_report_path or (
        _repo_root() / "data/validation/evidence/pilot-004/completion-report.json"
    )
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    quality = load_evidence_quality_review(quality_review_path)

    gate_excluded_sessions: Set[str] = set()
    gate_excluded_events: Set[str] = set()
    for run in quality.get("runs", []):
        classification = str(run.get("classification") or "")
        if classification in {"exploratory_only", "invalid_for_gate_calculation"}:
            if run.get("session_id"):
                gate_excluded_sessions.add(str(run["session_id"]))
            if run.get("shadow_event_id"):
                gate_excluded_events.add(str(run["shadow_event_id"]))

    included_sessions: List[str] = []
    included_events: List[str] = []
    for run in report.get("runs", []):
        sid = run.get("session_id")
        eid = run.get("shadow_event_id")
        if sid and str(sid) not in gate_excluded_sessions:
            included_sessions.append(str(sid))
        if eid and str(eid) not in gate_excluded_events:
            included_events.append(str(eid))

    duplicate_audit_path = _repo_root() / "data/validation/evidence/pilot-004/duplicate-metric-audit.json"
    excluded_fixture_events: List[str] = []
    if duplicate_audit_path.is_file():
        audit = json.loads(duplicate_audit_path.read_text(encoding="utf-8"))
        for case in audit.get("cases", []):
            if case.get("case") in CONTROLLED_DUPLICATE_FIXTURE_IDS:
                for key in ("shadow_event_id", "session_id"):
                    if case.get(key):
                        excluded_fixture_events.append(str(case[key]))

    return ValidationEvidenceScope(
        campaign_id="shadow-validation-pilot-004",
        included_shadow_event_ids=sorted(set(included_events)),
        included_session_ids=sorted(set(included_sessions)),
        included_setup_fixture_ids=["duplicate-metric-audit"],
        excluded_campaign_ids=sorted(EXCLUDED_CAMPAIGN_IDS),
        excluded_profile_ids=sorted(LEGACY_EXCLUDED_PROFILE_IDS),
        excluded_legacy_reason_codes=sorted(LEGACY_EXCLUSION_REASON_CODES),
        excluded_shadow_event_ids=sorted(set(excluded_fixture_events)),
        excluded_setup_fixture_ids=sorted(CONTROLLED_DUPLICATE_FIXTURE_IDS),
        excluded_session_ids=sorted(gate_excluded_sessions),
    )


def comparison_in_scope(
    *,
    comparison: Mapping[str, Any],
    scope: ValidationEvidenceScope,
    validation_run: Optional[Mapping[str, Any]] = None,
    candidates: Optional[List[Mapping[str, Any]]] = None,
) -> bool:
    event_id = str(comparison.get("shadow_event_id") or "")
    if scope.campaign_id:
        if event_id not in scope.included_shadow_event_id_set:
            return False
    elif scope.included_shadow_event_id_set and event_id not in scope.included_shadow_event_id_set:
        return False
    if event_id in scope.excluded_shadow_event_id_set:
        return False
    if validation_run:
        session_id = str(validation_run.get("session_id") or "")
        if session_id in scope.excluded_session_id_set:
            return False
        if scope.included_session_id_set and session_id not in scope.included_session_id_set:
            return False
    if candidates:
        for cand in candidates:
            if str(cand.get("profile_id") or "") in scope.excluded_profile_id_set:
                continue
            codes = cand.get("rejection_reason_codes")
            if isinstance(codes, str):
                try:
                    codes = json.loads(codes)
                except json.JSONDecodeError:
                    codes = []
            if any(str(c) in scope.excluded_legacy_reason_codes for c in (codes or [])):
                return False
    return True


def label_in_scope(label: Mapping[str, Any], scope: ValidationEvidenceScope) -> bool:
    event_id = str(label.get("shadow_event_id") or "")
    if scope.campaign_id:
        if event_id not in scope.included_shadow_event_id_set:
            return False
    elif scope.included_shadow_event_id_set and event_id not in scope.included_shadow_event_id_set:
        return False
    if event_id in scope.excluded_shadow_event_id_set:
        return False
    profile_id = label.get("profile_id")
    if profile_id and str(profile_id) in scope.excluded_profile_id_set:
        return False
    return True
