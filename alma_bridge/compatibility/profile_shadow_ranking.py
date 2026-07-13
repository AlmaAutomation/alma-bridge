from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from alma_bridge.compatibility.profile_shadow_models import ShadowCandidateEvaluation
from alma_bridge.learning.training import load_ranker_artifact, load_ranker_metadata
from alma_bridge.learning.ranker import predict_success_probability

RANKING_FORMULA_ID = "profile_shadow_rank_v1"
RANKING_FORMULA_VERSION = "1.0.0"


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def rank_eligible_candidates(
    *,
    candidates: List[ShadowCandidateEvaluation],
    profile_bundles: Mapping[str, Mapping[str, Any]],
    file_path: str,
    hardware: Mapping[str, Any],
) -> List[ShadowCandidateEvaluation]:
    eligible = [c for c in candidates if c.eligibility_status == "eligible"]
    if not eligible:
        return candidates

    artifact = load_ranker_artifact()
    metadata = load_ranker_metadata() or {}
    model_version = str(metadata.get("model_version") or metadata.get("version") or "")

    ranked: List[ShadowCandidateEvaluation] = []
    now = datetime.now(timezone.utc)

    for candidate in candidates:
        if candidate.eligibility_status != "eligible":
            ranked.append(candidate)
            continue

        bundle = profile_bundles[candidate.profile_id]
        profile = bundle["profile"]
        verification = bundle.get("verification") or {}

        host_dims = candidate.host_match_dimensions
        program_match = 1.0 if host_dims.get("program_identity_key_match") else 0.0
        host_match = 1.0 if host_dims.get("host_compatibility_class_id_match") else 0.0
        if host_match < 1.0:
            host_match = 0.5 if host_dims.get("host_arch_match") else 0.0

        bridge_family_match = 1.0 if profile.get("bridge_family_key") else 0.0
        drift_penalty = min(
            1.0,
            sum(d.severity for d in candidate.drift_dimensions if d.status == "drift") * 0.2,
        )
        environment_match = max(0.0, 1.0 - drift_penalty)
        verification_confidence = float(verification.get("confidence") or profile.get("aggregate_confidence") or 0.0)

        trust_cap = {
            "locally_verified": 1.0,
            "reused_successfully": 0.9,
            "imported": 0.3,
            "manually_modified": 0.2,
            "shadow_only": 0.2,
        }.get(candidate.trust_state, 0.1)

        success_count = int(profile.get("reuse_success_count") or 0)
        failure_count = int(profile.get("reuse_failure_count") or 0)
        total = success_count + failure_count
        reuse_rate = (success_count / total) if total else 0.5
        failure_penalty = min(0.5, failure_count * 0.05)

        verified_at = _parse_iso(profile.get("verified_at"))
        recency = 0.5
        if verified_at:
            age_days = max(0.0, (now - verified_at).total_seconds() / 86400.0)
            recency = max(0.1, 1.0 - min(age_days / 180.0, 0.9))

        ml_raw_score: Optional[float] = None
        ml_feature_vector: Optional[Dict[str, Any]] = None
        ml_component = 0.0
        if artifact:
            try:
                ml_raw_score = predict_success_probability(
                    artifact,
                    strategy_id=str(profile.get("strategy_id") or ""),
                    runtime="wine",
                    file_path=file_path,
                    hardware_profile=dict(hardware),
                    error_signature=None,
                )
                ml_feature_vector = {
                    "strategy_id": profile.get("strategy_id"),
                    "runtime": "wine",
                    "file_path": file_path,
                }
                ml_component = min(0.15, max(0.0, float(ml_raw_score)) * 0.15)
            except Exception:  # noqa: BLE001
                ml_raw_score = None
                ml_component = 0.0

        components = {
            "program_identity_match": round(program_match, 4),
            "host_class_match": round(host_match, 4),
            "bridge_family_match": round(bridge_family_match, 4),
            "environment_match_confidence": round(environment_match, 4),
            "verification_confidence": round(verification_confidence, 4),
            "trust_state_cap": round(trust_cap, 4),
            "reuse_success_rate": round(reuse_rate, 4),
            "recency": round(recency, 4),
            "failure_penalty": round(failure_penalty, 4),
            "drift_penalty": round(drift_penalty, 4),
            "ml_component": round(ml_component, 4),
        }

        final_score = (
            components["program_identity_match"] * 0.20
            + components["host_class_match"] * 0.15
            + components["bridge_family_match"] * 0.10
            + components["environment_match_confidence"] * 0.10
            + components["verification_confidence"] * 0.10
            + components["trust_state_cap"] * 0.10
            + components["reuse_success_rate"] * 0.08
            + components["recency"] * 0.07
            - components["failure_penalty"]
            - components["drift_penalty"]
            + components["ml_component"]
        )
        final_score = round(max(0.0, min(1.5, final_score)), 4)

        ranked.append(
            ShadowCandidateEvaluation(
                profile_id=candidate.profile_id,
                profile_revision=candidate.profile_revision,
                lifecycle_state=candidate.lifecycle_state,
                trust_state=candidate.trust_state,
                eligibility_status=candidate.eligibility_status,
                trust_category=candidate.trust_category,
                rejection_reason_codes=candidate.rejection_reason_codes,
                scoped_invalidations_applied=candidate.scoped_invalidations_applied,
                host_match_dimensions=candidate.host_match_dimensions,
                bridge_family_match_dimensions=candidate.bridge_family_match_dimensions,
                verification_binding_compatible=candidate.verification_binding_compatible,
                drift_dimensions=candidate.drift_dimensions,
                drift_prediction_result=candidate.drift_prediction_result,
                ranking_status="ranked",
                ranking_components=components,
                ml_model_version=model_version or None,
                ml_feature_vector=ml_feature_vector,
                ml_raw_score=ml_raw_score,
                final_rank_score=final_score,
                winner_selectable=candidate.winner_selectable,
            )
        )

    return ranked


def select_predicted_winner(
    candidates: List[ShadowCandidateEvaluation],
    profile_bundles: Mapping[str, Mapping[str, Any]],
) -> tuple[Optional[str], Optional[int], Optional[str], List[Dict[str, str]]]:
    selectable = [
        c
        for c in candidates
        if c.winner_selectable and c.ranking_status == "ranked" and c.final_rank_score is not None
    ]
    if not selectable:
        return None, None, None, []

    winner = max(selectable, key=lambda c: c.final_rank_score or 0.0)
    bundle = profile_bundles[winner.profile_id]
    bridge = bundle.get("bridge") or {}
    remediation = json.loads(bridge.get("remediation_protocol_json") or "[]")
    strategy_id = str(bundle["profile"].get("strategy_id") or "")
    bridge_family_key = str(bundle["profile"].get("bridge_family_key") or "")
    return winner.profile_id, winner.profile_revision, strategy_id, remediation
