from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional

from alma_bridge.compatibility.profile_store import (
    _connect,
    ensure_profile_tables,
    get_profile_by_idempotency_key,
    load_candidate_for_session_attempt,
)


def build_shadow_comparison_metrics(
    *,
    prediction: Mapping[str, Any],
    candidates: List[Mapping[str, Any]],
    actual: Mapping[str, Any],
    profile_candidate_id: Optional[str] = None,
) -> Dict[str, Any]:
    predicted_profile_id = prediction.get("selected_profile_id")
    predicted_strategy = prediction.get("predicted_strategy_id")
    predicted_family = prediction.get("predicted_bridge_family_key")
    predicted_remediation = json.loads(prediction.get("predicted_remediation_protocol_json") or "[]")

    actual_success = bool(actual.get("actual_success"))
    actual_strategy = actual.get("actual_strategy_id")
    actual_family = actual.get("actual_bridge_family_key")
    actual_manifest = actual.get("actual_bridge_manifest_hash")
    actual_remediation = json.loads(actual.get("actual_remediation_protocol_json") or "[]")

    indeterminate = False
    indeterminate_reason: Optional[str] = None

    if not actual_success and not actual.get("failure_signature"):
        indeterminate = True
        indeterminate_reason = "insufficient_failure_evidence"

    predicted_profile_selected = 1 if predicted_profile_id else 0

    strategy_agreement: Optional[int] = None
    if actual_strategy and predicted_strategy:
        strategy_agreement = 1 if actual_strategy == predicted_strategy else 0
    elif not predicted_profile_id and not actual_success:
        strategy_agreement = 1
    elif not predicted_profile_id:
        indeterminate = True
        indeterminate_reason = indeterminate_reason or "no_predicted_winner"

    family_agreement: Optional[int] = None
    if actual_family and predicted_family:
        family_agreement = 1 if actual_family == predicted_family else 0

    remediation_overlap: Optional[float] = None
    if predicted_remediation and actual_remediation:
        predicted_ids = {item.get("id") for item in predicted_remediation if item.get("id")}
        actual_ids = {item.get("id") for item in actual_remediation if item.get("id")}
        if predicted_ids:
            remediation_overlap = round(len(predicted_ids & actual_ids) / len(predicted_ids), 4)

    manifest_agreement: Optional[int] = None
    if actual_manifest and predicted_profile_id:
        winner = next(
            (c for c in candidates if c.get("profile_id") == predicted_profile_id),
            None,
        )
        if winner:
            dims = json.loads(winner.get("bridge_family_match_dimensions_json") or "{}")
            predicted_manifest = dims.get("bridge_manifest_hash")
            if predicted_manifest:
                manifest_agreement = 1 if predicted_manifest == actual_manifest else 0

    eligible_winner = next(
        (
            c
            for c in candidates
            if c.get("profile_id") == predicted_profile_id
            and c.get("eligibility_status") == "eligible"
        ),
        None,
    )
    false_eligibility: Optional[int] = None
    false_rejection: Optional[int] = None
    if actual_success and predicted_profile_id and not eligible_winner:
        false_eligibility = 1
    if actual_success and not predicted_profile_id:
        rejected_with_match = [
            c
            for c in candidates
            if c.get("eligibility_status") == "rejected"
            and json.loads(c.get("rejection_reason_codes_json") or "[]")
        ]
        if rejected_with_match:
            false_rejection = 1

    rank_agreement: Optional[int] = None
    ranked = [
        c for c in candidates
        if c.get("ranking_status") == "ranked" and c.get("final_rank_score") is not None
    ]
    if ranked and actual_strategy:
        top = max(ranked, key=lambda c: c.get("final_rank_score") or 0.0)
        top_bundle_strategy = prediction.get("predicted_strategy_id")
        if top.get("profile_id") == predicted_profile_id:
            rank_agreement = 1
        elif top_bundle_strategy and actual_strategy == top_bundle_strategy:
            rank_agreement = 1
        elif predicted_profile_id:
            rank_agreement = 0

    drift_correct: Optional[int] = None
    if predicted_profile_id and actual_manifest:
        winner = next((c for c in candidates if c.get("profile_id") == predicted_profile_id), None)
        if winner:
            drift_result = winner.get("drift_prediction_result")
            if drift_result == "no_drift_detected" and actual_success:
                drift_correct = 1
            elif drift_result == "drift_detected" and not actual_success:
                drift_correct = 1
            elif drift_result in {"indeterminate", "no_manifest_signals"}:
                indeterminate = True
                indeterminate_reason = indeterminate_reason or "drift_prediction_indeterminate"

    duplicate_lineage = 0
    if profile_candidate_id and predicted_profile_id:
        promoted_profile_id: Optional[str] = None
        try:
            with _connect() as conn:
                ensure_profile_tables(conn)
                row = conn.execute(
                    "SELECT promoted_profile_id FROM compatibility_profile_candidates WHERE candidate_id = ?",
                    (profile_candidate_id,),
                ).fetchone()
                if row and row["promoted_profile_id"]:
                    promoted_profile_id = str(row["promoted_profile_id"])
        except Exception:  # noqa: BLE001
            promoted_profile_id = None
        if promoted_profile_id and promoted_profile_id != predicted_profile_id:
            duplicate_lineage = 1

    reconstruction_required = 1 if predicted_profile_id and actual_success else 0

    precision: Optional[int] = None
    if not indeterminate and actual_success and predicted_profile_id:
        precision = 1 if strategy_agreement == 1 else 0
    elif not indeterminate and actual_success and not predicted_profile_id:
        precision = 0

    return {
        "predicted_profile_selected": predicted_profile_selected,
        "predicted_strategy_agreement": strategy_agreement,
        "predicted_bridge_family_agreement": family_agreement,
        "predicted_remediation_overlap": remediation_overlap,
        "predicted_manifest_agreement": manifest_agreement,
        "predicted_eligibility_precision": precision,
        "false_eligibility": false_eligibility,
        "false_rejection": false_rejection,
        "rank_agreement": rank_agreement,
        "drift_prediction_correct": drift_correct,
        "actual_verification_success": 1 if actual_success else 0,
        "duplicate_predicted_lineage": duplicate_lineage,
        "reconstruction_required": reconstruction_required,
        "indeterminate": 1 if indeterminate else 0,
        "indeterminate_reason": indeterminate_reason,
    }
