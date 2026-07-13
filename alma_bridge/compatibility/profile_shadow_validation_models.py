from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

MANIFEST_SCHEMA_VERSION = "shadow_validation_manifest_v1"
LABEL_SCHEMA_VERSION = "shadow_label_v1"
FAILURE_ANALYSIS_SCHEMA_VERSION = "shadow_failure_analysis_v1"

VALID_LABEL_TYPES = frozenset(
    {
        "eligible_correct",
        "eligible_incorrect",
        "rejected_correct",
        "rejected_incorrect",
        "drift_correct",
        "drift_incorrect",
        "winner_correct",
        "winner_incorrect",
        "indeterminate",
    }
)

FAILURE_KINDS = frozenset(
    {
        "false_eligibility",
        "false_rejection",
        "incorrect_winner",
        "incorrect_drift",
    }
)

DEFECT_CATEGORIES = frozenset(
    {
        "fingerprint_defect",
        "host_class_defect",
        "eligibility_rule_defect",
        "invalidation_defect",
        "drift_inspection_defect",
        "ranking_defect",
        "insufficient_evidence",
        "data_quality_defect",
    }
)

SCENARIO_CATEGORIES = frozenset(
    {
        "A_stable_repeat_success",
        "B_relocated_executable",
        "C_compatible_host_drift",
        "D_incompatible_host_drift",
        "E_prefix_drift",
        "F_clean_prefix_reconstruction",
        "G_known_compatibility_failure",
        "H_unrelated_runtime_failure",
        "I_trust_state",
        "J_multiple_candidate_ranking",
    }
)


@dataclass(frozen=True)
class ShadowLabelInput:
    shadow_event_id: str
    label_type: str
    label_source: str
    reviewer: str
    reason: str
    profile_id: Optional[str] = None
    evidence_refs: Optional[List[str]] = None


@dataclass
class PromotionGateThresholds:
    min_comparisons: int = 50
    min_scenario_categories: int = 5
    min_program_kinds: int = 3
    min_drift_scenarios: int = 10
    min_rejection_scenarios: int = 10
    eligibility_precision_min: float = 0.95
    false_eligibility_rate_max: float = 0.05
    drift_false_positive_rate_max: float = 0.05
    strategy_or_family_agreement_min: float = 0.80
    rank_agreement_min: float = 0.80
