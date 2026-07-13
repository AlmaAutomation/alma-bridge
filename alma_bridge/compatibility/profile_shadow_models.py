from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional
from uuid import uuid4

PREDICTION_SCHEMA_VERSION = "shadow_prediction_v1"
ACTUAL_OUTCOME_SCHEMA_VERSION = "shadow_actual_v1"
COMPARISON_SCHEMA_VERSION = "shadow_comparison_v1"
SHADOW_EVALUATION_VERSION = "shadow_eval_v1"


@dataclass(frozen=True)
class ShadowPlanningInputs:
    session_id: str
    correlation_id: str
    file_path: str
    executable_hash: str
    hardware: Mapping[str, Any]
    wine_prefix: Optional[str] = None
    runtime_hint: Optional[str] = None
    preferred_strategy_id: Optional[str] = None
    feature_flags: Optional[Mapping[str, bool]] = None


@dataclass(frozen=True)
class ShadowActualInputs:
    session_id: str
    correlation_id: str
    terminal_session_state: str
    success: bool
    winning_attempt_number: Optional[int] = None
    actual_strategy_id: Optional[str] = None
    actual_bridge_family_key: Optional[str] = None
    actual_bridge_manifest_hash: Optional[str] = None
    actual_remediation_protocol: Optional[List[Dict[str, str]]] = None
    verification_policy_id: Optional[str] = None
    verification_policy_version: Optional[str] = None
    verification_result_ref: Optional[str] = None
    failure_signature: Optional[str] = None
    fallback_indicators: Optional[List[str]] = None
    escalation_indicators: Optional[List[str]] = None
    profile_candidate_id: Optional[str] = None
    completed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class DriftDimension:
    dimension: str
    status: str
    reason_code: str
    expected: Optional[Any] = None
    observed: Optional[Any] = None
    severity: float = 0.0


@dataclass(frozen=True)
class ShadowCandidateEvaluation:
    profile_id: str
    profile_revision: int
    lifecycle_state: str
    trust_state: str
    eligibility_status: str
    trust_category: str
    rejection_reason_codes: List[str] = field(default_factory=list)
    scoped_invalidations_applied: List[str] = field(default_factory=list)
    host_match_dimensions: Dict[str, Any] = field(default_factory=dict)
    bridge_family_match_dimensions: Dict[str, Any] = field(default_factory=dict)
    verification_binding_compatible: bool = False
    drift_dimensions: List[DriftDimension] = field(default_factory=list)
    drift_prediction_result: str = "unknown"
    ranking_status: str = "not_ranked"
    ranking_components: Dict[str, float] = field(default_factory=dict)
    ml_model_version: Optional[str] = None
    ml_feature_vector: Optional[Dict[str, Any]] = None
    ml_raw_score: Optional[float] = None
    final_rank_score: Optional[float] = None
    winner_selectable: bool = False


def new_shadow_event_id() -> str:
    return str(uuid4())


def new_actual_outcome_id() -> str:
    return str(uuid4())
