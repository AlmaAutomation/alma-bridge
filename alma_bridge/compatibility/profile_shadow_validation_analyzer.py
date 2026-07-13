from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional

from alma_bridge.compatibility.profile_shadow_validation_store import record_failure_analysis
from alma_bridge.compatibility.profile_store import _connect
from alma_bridge.compatibility.profile_shadow_store import ensure_shadow_tables
from alma_bridge.compatibility.profile_shadow_validation_store import ensure_validation_tables


def _load_comparison_bundle(shadow_event_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        ensure_shadow_tables(conn)
        ensure_validation_tables(conn)
        comparison = conn.execute(
            "SELECT * FROM compatibility_profile_shadow_comparisons WHERE shadow_event_id = ?",
            (shadow_event_id,),
        ).fetchone()
        if not comparison:
            return None
        prediction = conn.execute(
            "SELECT * FROM compatibility_profile_shadow_predictions WHERE shadow_event_id = ?",
            (shadow_event_id,),
        ).fetchone()
        actual = conn.execute(
            "SELECT * FROM compatibility_profile_shadow_actual_outcomes WHERE shadow_event_id = ?",
            (shadow_event_id,),
        ).fetchone()
        run = conn.execute(
            "SELECT * FROM compatibility_profile_shadow_validation_runs WHERE shadow_event_id = ?",
            (shadow_event_id,),
        ).fetchone()
        winner = None
        if prediction and prediction["selected_profile_id"]:
            winner = conn.execute(
                """
                SELECT * FROM compatibility_profile_shadow_candidates
                WHERE shadow_event_id = ? AND profile_id = ?
                """,
                (shadow_event_id, prediction["selected_profile_id"]),
            ).fetchone()
    return {
        "comparison": dict(comparison),
        "prediction": dict(prediction) if prediction else None,
        "actual": dict(actual) if actual else None,
        "run": dict(run) if run else None,
        "winner_candidate": dict(winner) if winner else None,
    }


def _classify_defect(failure_kind: str, comparison: Mapping[str, Any]) -> str:
    if int(comparison.get("indeterminate") or 0):
        return "insufficient_evidence"
    if failure_kind == "false_eligibility":
        return "eligibility_rule_defect"
    if failure_kind == "false_rejection":
        return "eligibility_rule_defect"
    if failure_kind == "incorrect_winner":
        return "ranking_defect"
    if failure_kind == "incorrect_drift":
        return "drift_inspection_defect"
    return "data_quality_defect"


class ShadowFailureAnalyzer:
    """Record failure analyses from labelable comparison evidence."""

    @staticmethod
    def analyze_and_record() -> List[str]:
        with _connect() as conn:
            ensure_shadow_tables(conn)
            ensure_validation_tables(conn)
            comparisons = conn.execute(
                """
                SELECT * FROM compatibility_profile_shadow_comparisons
                WHERE indeterminate = 0
                """
            ).fetchall()

        recorded: List[str] = []
        for row in comparisons:
            comparison = dict(row)
            event_id = str(comparison["shadow_event_id"])
            bundle = _load_comparison_bundle(event_id)
            if not bundle:
                continue

            failures: List[str] = []
            if int(comparison.get("false_eligibility") or 0) == 1:
                failures.append("false_eligibility")
            if int(comparison.get("false_rejection") or 0) == 1:
                failures.append("false_rejection")
            if comparison.get("rank_agreement") == 0:
                failures.append("incorrect_winner")
            if comparison.get("drift_prediction_correct") == 0:
                failures.append("incorrect_drift")

            winner = bundle.get("winner_candidate") or {}
            actual = bundle.get("actual") or {}
            run = bundle.get("run") or {}

            for failure_kind in failures:
                analysis_id = record_failure_analysis(
                    shadow_event_id=event_id,
                    failure_kind=failure_kind,
                    defect_category=_classify_defect(failure_kind, comparison),
                    scenario_category=run.get("scenario_category"),
                    profile_id=(bundle.get("prediction") or {}).get("selected_profile_id"),
                    profile_revision=(bundle.get("prediction") or {}).get(
                        "selected_profile_revision"
                    ),
                    eligibility_reasons=json.loads(
                        winner.get("rejection_reason_codes_json") or "[]"
                    ),
                    ranking_components=json.loads(
                        winner.get("ranking_components_json") or "{}"
                    ),
                    drift_dimensions=json.loads(winner.get("drift_dimensions_json") or "[]"),
                    actual_evidence={
                        "actual_success": actual.get("actual_success"),
                        "actual_strategy_id": actual.get("actual_strategy_id"),
                        "failure_signature": actual.get("failure_signature"),
                    },
                    verification_result_ref=actual.get("verification_result_ref"),
                    root_cause_classification=failure_kind,
                    proposed_correction="Review eligibility, drift, or ranking rule for scenario.",
                )
                recorded.append(analysis_id)
        return recorded
