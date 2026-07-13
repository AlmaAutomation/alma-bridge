from __future__ import annotations

import json
import math
from collections import defaultdict
from typing import Any, DefaultDict, Dict, List, Mapping, Optional, Tuple

from alma_bridge.compatibility.profile_shadow_validation_models import PromotionGateThresholds
from alma_bridge.compatibility.profile_shadow_validation_store import (
    ensure_validation_tables,
    list_failure_analyses,
    list_labels,
)
from alma_bridge.compatibility.profile_store import _connect, ensure_profile_tables
from alma_bridge.compatibility.profile_shadow_store import ensure_shadow_tables


def wilson_ci(successes: int, total: int, z: float = 1.96) -> Optional[Dict[str, float]]:
    if total <= 0:
        return None
    p = successes / total
    denom = 1 + (z * z) / total
    centre = p + (z * z) / (2 * total)
    margin = z * math.sqrt((p * (1 - p) + (z * z) / (4 * total)) / total)
    low = max(0.0, (centre - margin) / denom)
    high = min(1.0, (centre + margin) / denom)
    return {"low": round(low, 4), "high": round(high, 4), "n": total}


def _rate(numerator: int, denominator: int) -> Optional[float]:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _load_validation_rows() -> Dict[str, List[Dict[str, Any]]]:
    with _connect() as conn:
        ensure_profile_tables(conn)
        ensure_shadow_tables(conn)
        ensure_validation_tables(conn)
        predictions = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM compatibility_profile_shadow_predictions ORDER BY created_at"
            ).fetchall()
        ]
        comparisons = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM compatibility_profile_shadow_comparisons ORDER BY created_at"
            ).fetchall()
        ]
        actuals = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM compatibility_profile_shadow_actual_outcomes ORDER BY completed_at"
            ).fetchall()
        ]
        validation_runs = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM compatibility_profile_shadow_validation_runs ORDER BY registered_at"
            ).fetchall()
        ]
        events = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM compatibility_profile_shadow_events ORDER BY created_at"
            ).fetchall()
        ]
        candidates = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM compatibility_profile_shadow_candidates"
            ).fetchall()
        ]
    return {
        "predictions": predictions,
        "comparisons": comparisons,
        "actuals": actuals,
        "validation_runs": validation_runs,
        "events": events,
        "candidates": candidates,
    }


def _comparison_by_event(comparisons: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(c["shadow_event_id"]): c for c in comparisons}


def _prediction_by_event(predictions: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(p["shadow_event_id"]): p for p in predictions}


def _actual_by_event(actuals: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(a["shadow_event_id"]): a for a in actuals}


def _run_by_event(runs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(r["shadow_event_id"]): r for r in runs}


def _winner_candidate(
    candidates: List[Dict[str, Any]],
    profile_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    if not profile_id:
        return None
    for row in candidates:
        if str(row["profile_id"]) == str(profile_id):
            return row
    return None


def _labelable_comparisons(comparisons: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [c for c in comparisons if not int(c.get("indeterminate") or 0)]


def _build_dimension_context(
    *,
    prediction: Dict[str, Any],
    comparison: Optional[Dict[str, Any]],
    actual: Optional[Dict[str, Any]],
    run: Optional[Dict[str, Any]],
    winner_candidate: Optional[Dict[str, Any]],
) -> Dict[str, Optional[str]]:
    return {
        "program_kind": (run or {}).get("program_kind"),
        "strategy": (actual or {}).get("actual_strategy_id")
        or prediction.get("predicted_strategy_id"),
        "host_compatibility_class_id": prediction.get("host_compatibility_class_id"),
        "wine_major": None,
        "trust_state": (winner_candidate or {}).get("trust_state"),
        "drift_category": (winner_candidate or {}).get("drift_prediction_result"),
        "failure_signature": (actual or {}).get("failure_signature"),
        "application_family": (run or {}).get("application_family"),
        "scenario_category": (run or {}).get("scenario_category"),
    }


def _accumulate_breakdown(
    store: DefaultDict[str, Dict[str, Any]],
    key: str,
    *,
    labelable: bool,
    false_eligibility: bool = False,
    false_rejection: bool = False,
    strategy_agree: Optional[bool] = None,
    family_agree: Optional[bool] = None,
    rank_agree: Optional[bool] = None,
    drift_correct: Optional[bool] = None,
    indeterminate: bool = False,
) -> None:
    bucket = store[key]
    bucket["count"] = bucket.get("count", 0) + 1
    if indeterminate:
        bucket["indeterminate"] = bucket.get("indeterminate", 0) + 1
    if labelable:
        bucket["labelable"] = bucket.get("labelable", 0) + 1
    if false_eligibility:
        bucket["false_eligibility"] = bucket.get("false_eligibility", 0) + 1
    if false_rejection:
        bucket["false_rejection"] = bucket.get("false_rejection", 0) + 1
    if strategy_agree is True:
        bucket["strategy_agreement"] = bucket.get("strategy_agreement", 0) + 1
    if strategy_agree is False:
        bucket["strategy_disagreement"] = bucket.get("strategy_disagreement", 0) + 1
    if family_agree is True:
        bucket["family_agreement"] = bucket.get("family_agreement", 0) + 1
    if rank_agree is True:
        bucket["rank_agreement"] = bucket.get("rank_agreement", 0) + 1
    if drift_correct is True:
        bucket["drift_correct"] = bucket.get("drift_correct", 0) + 1
    if drift_correct is False:
        bucket["drift_incorrect"] = bucket.get("drift_incorrect", 0) + 1


class ShadowValidationReporter:
    """Read-only shadow validation reporting."""

    @staticmethod
    def generate_report() -> Dict[str, Any]:
        rows = _load_validation_rows()
        predictions = rows["predictions"]
        comparisons = rows["comparisons"]
        actuals = rows["actuals"]
        events = rows["events"]
        validation_runs = rows["validation_runs"]
        candidates = rows["candidates"]

        pred_by_event = _prediction_by_event(predictions)
        comp_by_event = _comparison_by_event(comparisons)
        actual_by_event = _actual_by_event(actuals)
        run_by_event = _run_by_event(validation_runs)
        labels = list_labels()

        candidates_by_event: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
        for candidate in candidates:
            candidates_by_event[str(candidate["shadow_event_id"])].append(candidate)

        labelable = _labelable_comparisons(comparisons)
        indeterminate_count = len(comparisons) - len(labelable)

        counts = {
            "total_shadow_predictions": len(predictions),
            "predictions_with_no_candidates": sum(
                1 for p in predictions if int(p.get("candidate_count") or 0) == 0
            ),
            "predictions_with_eligible_candidates": sum(
                1 for p in predictions if int(p.get("eligible_count") or 0) > 0
            ),
            "predictions_with_selected_winners": sum(
                1 for p in predictions if p.get("selected_profile_id")
            ),
            "actual_outcomes_recorded": len(actuals),
            "comparisons_completed": len(comparisons),
            "indeterminate_comparisons": indeterminate_count,
            "prediction_persistence_failures": sum(
                1 for e in events if e.get("event_type") == "shadow_prediction_failed"
            ),
            "actual_outcome_persistence_failures": sum(
                1 for e in events if e.get("event_type") == "shadow_actual_persist_failed"
            ),
            "validation_runs_registered": len(validation_runs),
            "labels_recorded": len(labels),
        }

        false_eligibility = sum(
            1 for c in labelable if int(c.get("false_eligibility") or 0) == 1
        )
        false_rejection = sum(
            1 for c in labelable if int(c.get("false_rejection") or 0) == 1
        )
        strategy_agreement = sum(
            1
            for c in labelable
            if c.get("predicted_strategy_agreement") == 1
        )
        family_agreement = sum(
            1
            for c in labelable
            if c.get("predicted_bridge_family_agreement") == 1
        )
        rank_agreement = sum(
            1 for c in labelable if c.get("rank_agreement") == 1
        )
        drift_correct = sum(
            1 for c in labelable if c.get("drift_prediction_correct") == 1
        )
        drift_labelable = [
            c for c in labelable if c.get("drift_prediction_correct") is not None
        ]
        drift_incorrect = sum(
            1 for c in drift_labelable if int(c.get("drift_prediction_correct") or 0) == 0
        )

        winner_comparisons = [
            c
            for c in labelable
            if int(c.get("predicted_profile_selected") or 0) == 1
        ]
        verification_success_with_winner = sum(
            1
            for c in winner_comparisons if int(c.get("actual_verification_success") or 0) == 1
        )
        duplicate_lineage = sum(
            1 for c in labelable if int(c.get("duplicate_predicted_lineage") or 0) == 1
        )

        remediation_overlaps = [
            float(c["predicted_remediation_overlap"])
            for c in labelable
            if c.get("predicted_remediation_overlap") is not None
        ]
        avg_remediation_overlap = (
            round(sum(remediation_overlaps) / len(remediation_overlaps), 4)
            if remediation_overlaps
            else None
        )

        eligible_label_correct = sum(
            1 for label in labels if label.get("label_type") == "eligible_correct"
        )
        eligible_label_incorrect = sum(
            1 for label in labels if label.get("label_type") == "eligible_incorrect"
        )
        rejected_label_correct = sum(
            1 for label in labels if label.get("label_type") == "rejected_correct"
        )
        rejected_label_incorrect = sum(
            1 for label in labels if label.get("label_type") == "rejected_incorrect"
        )

        label_eligible_den = eligible_label_correct + eligible_label_incorrect
        label_rejected_den = rejected_label_correct + rejected_label_incorrect

        metrics = {
            "eligibility_precision": _rate(
                eligible_label_correct,
                label_eligible_den,
            )
            if label_eligible_den
            else _rate(
                sum(1 for c in labelable if int(c.get("predicted_eligibility_precision") or 0) == 1),
                len([c for c in labelable if c.get("predicted_eligibility_precision") is not None]),
            ),
            "eligibility_recall": _rate(
                eligible_label_correct,
                eligible_label_correct + rejected_label_incorrect,
            )
            if (eligible_label_correct + rejected_label_incorrect) > 0
            else None,
            "false_eligibility_count": false_eligibility,
            "false_eligibility_rate": _rate(false_eligibility, len(labelable)),
            "false_rejection_count": false_rejection,
            "false_rejection_rate": _rate(false_rejection, len(labelable)),
            "strategy_agreement_rate": _rate(strategy_agreement, len(labelable)),
            "bridge_family_agreement_rate": _rate(family_agreement, len(labelable)),
            "remediation_overlap_avg": avg_remediation_overlap,
            "rank_agreement_rate": _rate(
                rank_agreement,
                len([c for c in labelable if c.get("rank_agreement") is not None]),
            ),
            "drift_prediction_precision": _rate(drift_correct, len(drift_labelable)),
            "drift_false_positive_rate": _rate(drift_incorrect, len(drift_labelable)),
            "verification_success_rate_with_predicted_winner": _rate(
                verification_success_with_winner,
                len(winner_comparisons),
            ),
            "profile_creation_duplicate_rate": _rate(duplicate_lineage, len(labelable)),
            "insufficient_evidence_rate": _rate(indeterminate_count, len(comparisons)),
            "confidence_intervals": {
                "eligibility_precision": wilson_ci(
                    eligible_label_correct or sum(
                        1
                        for c in labelable
                        if int(c.get("predicted_eligibility_precision") or 0) == 1
                    ),
                    label_eligible_den or len(labelable),
                ),
                "false_eligibility_rate": wilson_ci(false_eligibility, len(labelable)),
                "strategy_agreement": wilson_ci(strategy_agreement, len(labelable)),
                "rank_agreement": wilson_ci(
                    rank_agreement,
                    len([c for c in labelable if c.get("rank_agreement") is not None]),
                ),
            },
        }

        breakdowns: Dict[str, Dict[str, Any]] = {
            "by_program_kind": {},
            "by_strategy": {},
            "by_host_compatibility_class": {},
            "by_trust_state": {},
            "by_drift_category": {},
            "by_failure_signature": {},
            "by_application_family": {},
            "by_scenario_category": {},
        }

        for comparison in comparisons:
            event_id = str(comparison["shadow_event_id"])
            prediction = pred_by_event.get(event_id, {})
            actual = actual_by_event.get(event_id)
            run = run_by_event.get(event_id)
            winner = _winner_candidate(
                candidates_by_event.get(event_id, []),
                prediction.get("selected_profile_id"),
            )
            ctx = _build_dimension_context(
                prediction=prediction,
                comparison=comparison,
                actual=actual,
                run=run,
                winner_candidate=winner,
            )
            is_labelable = not int(comparison.get("indeterminate") or 0)
            fe = is_labelable and int(comparison.get("false_eligibility") or 0) == 1
            fr = is_labelable and int(comparison.get("false_rejection") or 0) == 1
            sa = comparison.get("predicted_strategy_agreement")
            fa = comparison.get("predicted_bridge_family_agreement")
            ra = comparison.get("rank_agreement")
            dc = comparison.get("drift_prediction_correct")

            dim_map = {
                "program_kind": "by_program_kind",
                "strategy": "by_strategy",
                "host_compatibility_class_id": "by_host_compatibility_class",
                "trust_state": "by_trust_state",
                "drift_category": "by_drift_category",
                "failure_signature": "by_failure_signature",
                "application_family": "by_application_family",
                "scenario_category": "by_scenario_category",
            }
            for dim_key, bucket_name in dim_map.items():
                if dim_key == "scenario_category":
                    key = str(ctx.get("scenario_category") or "unregistered")
                else:
                    key = str(ctx.get(dim_key) or "unknown")
                store = breakdowns[bucket_name]
                if key not in store:
                    store[key] = {}
                _accumulate_breakdown(
                    store,
                    key,
                    labelable=is_labelable,
                    false_eligibility=fe,
                    false_rejection=fr,
                    strategy_agree=True if sa == 1 else False if sa == 0 else None,
                    family_agree=True if fa == 1 else False if fa == 0 else None,
                    rank_agree=True if ra == 1 else False if ra == 0 else None,
                    drift_correct=True if dc == 1 else False if dc == 0 else None,
                    indeterminate=not is_labelable,
                )

        for bucket in breakdowns.values():
            for key, data in bucket.items():
                labelable_n = data.get("labelable", 0)
                data["false_eligibility_rate"] = _rate(
                    data.get("false_eligibility", 0), labelable_n
                )
                data["false_rejection_rate"] = _rate(
                    data.get("false_rejection", 0), labelable_n
                )
                data["strategy_agreement_rate"] = _rate(
                    data.get("strategy_agreement", 0),
                    data.get("strategy_agreement", 0) + data.get("strategy_disagreement", 0),
                )

        diversity = {
            "scenario_categories": sorted(
                {str(r.get("scenario_category")) for r in validation_runs if r.get("scenario_category")}
            ),
            "scenario_category_count": len(
                {str(r.get("scenario_category")) for r in validation_runs if r.get("scenario_category")}
            ),
            "program_kinds": sorted(
                {str(r.get("program_kind")) for r in validation_runs if r.get("program_kind")}
            ),
            "program_kind_count": len(
                {str(r.get("program_kind")) for r in validation_runs if r.get("program_kind")}
            ),
            "drift_scenarios": sum(
                1
                for r in validation_runs
                if str(r.get("scenario_category") or "").startswith("E_")
            ),
            "rejection_scenarios": sum(
                1
                for r in validation_runs
                if str(r.get("scenario_category") or "")
                in {"D_incompatible_host_drift", "I_trust_state"}
            ),
        }

        promotion = evaluate_promotion_gates(
            counts=counts,
            metrics=metrics,
            diversity=diversity,
            breakdowns=breakdowns,
        )

        failures = list_failure_analyses()

        return {
            "counts": counts,
            "metrics": metrics,
            "diversity": diversity,
            "breakdowns": breakdowns,
            "promotion_gates": promotion,
            "failure_analyses": failures,
            "labels_summary": {
                "eligible_correct": eligible_label_correct,
                "eligible_incorrect": eligible_label_incorrect,
                "rejected_correct": rejected_label_correct,
                "rejected_incorrect": rejected_label_incorrect,
            },
        }


def evaluate_promotion_gates(
    *,
    counts: Mapping[str, Any],
    metrics: Mapping[str, Any],
    diversity: Mapping[str, Any],
    breakdowns: Mapping[str, Mapping[str, Any]],
    thresholds: Optional[PromotionGateThresholds] = None,
) -> Dict[str, Any]:
    gates = thresholds or PromotionGateThresholds()
    labelable_comparisons = counts.get("comparisons_completed", 0) - counts.get(
        "indeterminate_comparisons", 0
    )

    checks: Dict[str, Dict[str, Any]] = {
        "min_comparisons": {
            "required": gates.min_comparisons,
            "actual": labelable_comparisons,
            "passed": labelable_comparisons >= gates.min_comparisons,
        },
        "min_scenario_categories": {
            "required": gates.min_scenario_categories,
            "actual": diversity.get("scenario_category_count", 0),
            "passed": diversity.get("scenario_category_count", 0) >= gates.min_scenario_categories,
        },
        "min_program_kinds": {
            "required": gates.min_program_kinds,
            "actual": diversity.get("program_kind_count", 0),
            "passed": diversity.get("program_kind_count", 0) >= gates.min_program_kinds,
        },
        "min_drift_scenarios": {
            "required": gates.min_drift_scenarios,
            "actual": diversity.get("drift_scenarios", 0),
            "passed": diversity.get("drift_scenarios", 0) >= gates.min_drift_scenarios,
        },
        "min_rejection_scenarios": {
            "required": gates.min_rejection_scenarios,
            "actual": diversity.get("rejection_scenarios", 0),
            "passed": diversity.get("rejection_scenarios", 0) >= gates.min_rejection_scenarios,
        },
        "eligibility_precision": {
            "required": gates.eligibility_precision_min,
            "actual": metrics.get("eligibility_precision"),
            "passed": (
                metrics.get("eligibility_precision") is not None
                and metrics["eligibility_precision"] >= gates.eligibility_precision_min
            ),
        },
        "false_eligibility_rate": {
            "required_max": gates.false_eligibility_rate_max,
            "actual": metrics.get("false_eligibility_rate"),
            "passed": (
                metrics.get("false_eligibility_rate") is not None
                and metrics["false_eligibility_rate"] <= gates.false_eligibility_rate_max
            ),
        },
        "drift_false_positive_rate": {
            "required_max": gates.drift_false_positive_rate_max,
            "actual": metrics.get("drift_false_positive_rate"),
            "passed": (
                metrics.get("drift_false_positive_rate") is not None
                and metrics["drift_false_positive_rate"] <= gates.drift_false_positive_rate_max
            ),
        },
        "strategy_or_family_agreement": {
            "required": gates.strategy_or_family_agreement_min,
            "actual": max(
                metrics.get("strategy_agreement_rate") or 0,
                metrics.get("bridge_family_agreement_rate") or 0,
            ),
            "passed": (
                max(
                    metrics.get("strategy_agreement_rate") or 0,
                    metrics.get("bridge_family_agreement_rate") or 0,
                )
                >= gates.strategy_or_family_agreement_min
            ),
        },
        "rank_agreement_multi_candidate": {
            "required": gates.rank_agreement_min,
            "actual": metrics.get("rank_agreement_rate"),
            "passed": (
                metrics.get("rank_agreement_rate") is not None
                and metrics["rank_agreement_rate"] >= gates.rank_agreement_min
            ),
        },
        "no_duplicate_profile_defects": {
            "required": 0,
            "actual": metrics.get("profile_creation_duplicate_rate"),
            "passed": (metrics.get("profile_creation_duplicate_rate") or 0) == 0,
        },
    }

    category_failures: List[Dict[str, Any]] = []
    by_category = breakdowns.get("by_scenario_category", {})
    for category, data in by_category.items():
        if category == "unregistered":
            continue
        labelable_n = data.get("labelable", 0)
        if labelable_n < 3:
            continue
        fer = data.get("false_eligibility_rate")
        if fer is not None and fer > gates.false_eligibility_rate_max:
            category_failures.append(
                {
                    "scenario_category": category,
                    "issue": "false_eligibility_rate_exceeded",
                    "rate": fer,
                    "labelable_n": labelable_n,
                }
            )
        sar = data.get("strategy_agreement_rate")
        if sar is not None and sar < gates.strategy_or_family_agreement_min:
            category_failures.append(
                {
                    "scenario_category": category,
                    "issue": "strategy_agreement_below_threshold",
                    "rate": sar,
                    "labelable_n": labelable_n,
                }
            )

    aggregate_passed = all(check["passed"] for check in checks.values())
    category_passed = len(category_failures) == 0
    overall_passed = aggregate_passed and category_passed

    return {
        "thresholds": gates.__dict__,
        "checks": checks,
        "category_failures": category_failures,
        "aggregate_passed": aggregate_passed,
        "category_passed": category_passed,
        "promotion_ready": overall_passed,
        "active_reuse_technically_justified": overall_passed,
        "recommendation": (
            "Active reuse is technically justified based on current shadow evidence."
            if overall_passed
            else "Active reuse is NOT justified. Address failing gates and per-category issues, then repeat shadow validation."
        ),
    }
