from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from alma_bridge.compatibility.profile_fingerprints import (
    build_program_identity_key,
    build_program_identity_payload,
)
from alma_bridge.compatibility.profile_host_class import (
    build_host_compatibility_class_id,
    build_host_compatibility_class_payload,
)
from alma_bridge.compatibility.profile_metrics import (
    increment_profile_counter,
    log_profile_event,
)
from alma_bridge.compatibility.profile_shadow_comparison import build_shadow_comparison_metrics
from alma_bridge.compatibility.expected_verification_contract import (
    expected_verification_contract_for_kind,
)
from alma_bridge.compatibility.profile_shadow_eligibility import evaluate_candidate_eligibility
from alma_bridge.compatibility.profile_shadow_models import (
    ShadowActualInputs,
    ShadowPlanningInputs,
    new_actual_outcome_id,
    new_shadow_event_id,
)
from alma_bridge.compatibility.profile_shadow_ranking import (
    RANKING_FORMULA_ID,
    RANKING_FORMULA_VERSION,
    rank_eligible_candidates,
    select_predicted_winner,
)
from alma_bridge.compatibility.profile_shadow_store import (
    init_shadow_store,
    load_shadow_candidates,
    load_shadow_prediction,
    persist_shadow_actual_outcome,
    persist_shadow_comparison,
    persist_shadow_prediction,
    record_shadow_event,
)
from alma_bridge.compatibility.profile_store import (
    list_profile_bundles_for_executable,
    load_candidate_for_session_attempt,
)
from alma_bridge.compatibility.program_kind import classify_program_kind
from alma_bridge.config import settings
from alma_bridge.learning.training import load_ranker_metadata

logger = logging.getLogger(__name__)


def shadow_mode_enabled() -> bool:
    return bool(
        settings.compatibility_profiles_enabled
        and settings.compatibility_profile_shadow_mode
    )


class ProfileShadowService:
    """Observe-only shadow profile matching. Never controls execution."""

    @staticmethod
    def create_prediction(inputs: ShadowPlanningInputs) -> Optional[str]:
        if not shadow_mode_enabled():
            return None

        existing = load_shadow_prediction(inputs.session_id)
        if existing:
            return str(existing["shadow_event_id"])

        shadow_event_id = new_shadow_event_id()
        try:
            kind = classify_program_kind(
                inputs.file_path,
                host_arch=str(inputs.hardware.get("architecture") or "x86_64"),
            )
            program_payload = build_program_identity_payload(
                executable_hash=inputs.executable_hash,
                executable_format=str(kind.get("binary_format") or "unknown"),
                architecture=str(inputs.hardware.get("architecture") or "x86_64"),
                program_kind=str(kind.get("program_kind") or "unknown"),
            )
            program_identity_key = build_program_identity_key(program_payload)
            host_payload = build_host_compatibility_class_payload(
                inputs.hardware,
                program_needs_gpu=bool(kind.get("needs_gui")),
            )
            if inputs.host_payload_overlay:
                host_payload = {**host_payload, **dict(inputs.host_payload_overlay)}
            host_class_id = build_host_compatibility_class_id(host_payload)
            expected_verification = expected_verification_contract_for_kind(kind)

            bundles = list_profile_bundles_for_executable(inputs.executable_hash)
            profile_bundles = {str(b["profile"]["profile_id"]): b for b in bundles}

            candidates = []
            for bundle in bundles:
                evaluation = evaluate_candidate_eligibility(
                    profile_bundle=bundle,
                    program_identity_key=program_identity_key,
                    host_compatibility_class_id=host_class_id,
                    host_payload=host_payload,
                    expected_verification=expected_verification,
                    active_invalidations=bundle.get("invalidations"),
                    wine_prefix=inputs.wine_prefix,
                )
                candidates.append(evaluation)
                if evaluation.eligibility_status == "eligible":
                    increment_profile_counter("shadow_candidate_eligible")
                    log_profile_event(
                        "shadow_candidate_eligible",
                        session_id=inputs.session_id,
                        profile_id=evaluation.profile_id,
                        revision=evaluation.profile_revision,
                    )
                else:
                    for reason in evaluation.rejection_reason_codes:
                        increment_profile_counter(f"shadow_candidate_rejected_{reason}")
                    log_profile_event(
                        "shadow_candidate_rejected",
                        session_id=inputs.session_id,
                        profile_id=evaluation.profile_id,
                        reasons=evaluation.rejection_reason_codes,
                    )
                increment_profile_counter("shadow_candidate_evaluated")

            ranking_status = "completed"
            try:
                candidates = rank_eligible_candidates(
                    candidates=candidates,
                    profile_bundles=profile_bundles,
                    file_path=inputs.file_path,
                    hardware=inputs.hardware,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("shadow ranking failed session=%s", inputs.session_id)
                ranking_status = "failed"
                record_shadow_event(
                    session_id=inputs.session_id,
                    event_type="shadow_ranking_failed",
                    shadow_event_id=shadow_event_id,
                    error=str(exc),
                )

            winner_id, winner_revision, predicted_strategy, predicted_remediation = (
                select_predicted_winner(candidates, profile_bundles)
            )
            predicted_family = None
            if winner_id and winner_id in profile_bundles:
                predicted_family = str(
                    profile_bundles[winner_id]["profile"].get("bridge_family_key") or ""
                )

            metadata = load_ranker_metadata() or {}
            model_version = str(metadata.get("model_version") or metadata.get("version") or "")

            feature_flags = dict(inputs.feature_flags or {})
            feature_flags.setdefault(
                "compatibility_profiles_enabled",
                settings.compatibility_profiles_enabled,
            )
            feature_flags.setdefault(
                "compatibility_profile_shadow_mode",
                settings.compatibility_profile_shadow_mode,
            )
            feature_flags.setdefault(
                "compatibility_profile_creation_enabled",
                settings.compatibility_profile_creation_enabled,
            )
            if inputs.host_payload_overlay:
                feature_flags["shadow_host_payload_overlay"] = dict(inputs.host_payload_overlay)
                feature_flags["effective_host_compatibility_class_payload"] = dict(host_payload)

            persist_shadow_prediction(
                shadow_event_id=shadow_event_id,
                session_id=inputs.session_id,
                correlation_id=inputs.correlation_id,
                program_identity_key=program_identity_key,
                executable_hash=inputs.executable_hash,
                host_compatibility_class_id=host_class_id,
                ranking_formula_id=RANKING_FORMULA_ID,
                ranking_formula_version=RANKING_FORMULA_VERSION,
                ranking_status=ranking_status,
                selected_profile_id=winner_id,
                selected_profile_revision=winner_revision,
                predicted_strategy_id=predicted_strategy,
                predicted_bridge_family_key=predicted_family,
                predicted_remediation_protocol=predicted_remediation,
                feature_flags=feature_flags,
                model_version=model_version or None,
                candidates=candidates,
            )

            if winner_id:
                increment_profile_counter("shadow_winner_selected")
                log_profile_event(
                    "shadow_winner_selected",
                    session_id=inputs.session_id,
                    shadow_event_id=shadow_event_id,
                    profile_id=winner_id,
                    revision=winner_revision,
                    ranking_formula_version=RANKING_FORMULA_VERSION,
                )
            else:
                increment_profile_counter("shadow_no_winner")
                log_profile_event(
                    "shadow_no_winner",
                    session_id=inputs.session_id,
                    shadow_event_id=shadow_event_id,
                )

            increment_profile_counter("shadow_prediction_created")
            log_profile_event(
                "shadow_prediction_created",
                session_id=inputs.session_id,
                shadow_event_id=shadow_event_id,
                ranking_formula_version=RANKING_FORMULA_VERSION,
            )
            return shadow_event_id
        except Exception as exc:  # noqa: BLE001
            logger.exception("shadow prediction failed session=%s", inputs.session_id)
            increment_profile_counter("shadow_prediction_failed")
            record_shadow_event(
                session_id=inputs.session_id,
                event_type="shadow_prediction_failed",
                shadow_event_id=shadow_event_id,
                error=str(exc),
            )
            log_profile_event(
                "shadow_prediction_failed",
                session_id=inputs.session_id,
                error=str(exc),
            )
            return None

    @staticmethod
    def record_actual_outcome(inputs: ShadowActualInputs) -> Optional[str]:
        if not shadow_mode_enabled():
            return None

        prediction = load_shadow_prediction(inputs.session_id)
        if not prediction:
            return None

        shadow_event_id = str(prediction["shadow_event_id"])
        actual_outcome_id = new_actual_outcome_id()
        try:
            persist_shadow_actual_outcome(
                actual_outcome_id=actual_outcome_id,
                shadow_event_id=shadow_event_id,
                session_id=inputs.session_id,
                terminal_session_state=inputs.terminal_session_state,
                actual_success=inputs.success,
                actual_strategy_id=inputs.actual_strategy_id,
                actual_bridge_family_key=inputs.actual_bridge_family_key,
                actual_bridge_manifest_hash=inputs.actual_bridge_manifest_hash,
                actual_remediation_protocol=inputs.actual_remediation_protocol,
                winning_attempt_number=inputs.winning_attempt_number,
                verification_result_ref=inputs.verification_result_ref,
                verification_policy_id=inputs.verification_policy_id,
                verification_policy_version=inputs.verification_policy_version,
                failure_signature=inputs.failure_signature,
                fallback_indicators=inputs.fallback_indicators,
                escalation_indicators=inputs.escalation_indicators,
                profile_candidate_id=inputs.profile_candidate_id,
                completed_at=inputs.completed_at,
            )

            candidates = load_shadow_candidates(shadow_event_id)
            candidate_id = inputs.profile_candidate_id
            if not candidate_id and inputs.winning_attempt_number:
                snap = load_candidate_for_session_attempt(
                    inputs.session_id,
                    inputs.winning_attempt_number,
                )
                if snap:
                    candidate_id = snap.candidate_id

            metrics = build_shadow_comparison_metrics(
                prediction=prediction,
                candidates=candidates,
                actual={
                    "actual_success": inputs.success,
                    "actual_strategy_id": inputs.actual_strategy_id,
                    "actual_bridge_family_key": inputs.actual_bridge_family_key,
                    "actual_bridge_manifest_hash": inputs.actual_bridge_manifest_hash,
                    "actual_remediation_protocol_json": (
                        __import__("json").dumps(inputs.actual_remediation_protocol or [])
                    ),
                    "failure_signature": inputs.failure_signature,
                },
                profile_candidate_id=candidate_id,
            )
            persist_shadow_comparison(
                shadow_event_id=shadow_event_id,
                actual_outcome_id=actual_outcome_id,
                session_id=inputs.session_id,
                metrics=metrics,
            )

            if metrics.get("indeterminate"):
                increment_profile_counter("shadow_indeterminate")
            if metrics.get("predicted_strategy_agreement") == 1:
                increment_profile_counter("shadow_strategy_agreement")
            if metrics.get("rank_agreement") == 1:
                increment_profile_counter("shadow_rank_agreement")
            if metrics.get("false_eligibility") == 1:
                increment_profile_counter("shadow_false_eligibility")
            if metrics.get("false_rejection") == 1:
                increment_profile_counter("shadow_false_rejection")
            if metrics.get("drift_prediction_correct") == 1:
                increment_profile_counter("shadow_drift_prediction_correct")

            increment_profile_counter("shadow_comparison_created")
            increment_profile_counter("shadow_actual_recorded")
            log_profile_event(
                "shadow_actual_recorded",
                session_id=inputs.session_id,
                shadow_event_id=shadow_event_id,
                actual_outcome_id=actual_outcome_id,
            )
            log_profile_event(
                "shadow_comparison_created",
                session_id=inputs.session_id,
                shadow_event_id=shadow_event_id,
                indeterminate=metrics.get("indeterminate"),
            )
            return actual_outcome_id
        except Exception as exc:  # noqa: BLE001
            logger.exception("shadow actual persist failed session=%s", inputs.session_id)
            increment_profile_counter("shadow_actual_persist_failed")
            record_shadow_event(
                session_id=inputs.session_id,
                event_type="shadow_actual_persist_failed",
                shadow_event_id=shadow_event_id,
                error=str(exc),
            )
            log_profile_event(
                "shadow_actual_persist_failed",
                session_id=inputs.session_id,
                error=str(exc),
            )
            return None


def init_profile_shadow_infrastructure() -> None:
    init_shadow_store()
    from alma_bridge.compatibility.profile_shadow_validation_store import init_validation_store

    init_validation_store()
