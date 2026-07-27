from __future__ import annotations

"""Ranking explanation and active-reuse safety classification."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional


class RankingSelectionReasonCode(str, Enum):
    SINGLE_ELIGIBLE_CANDIDATE = "SINGLE_ELIGIBLE_CANDIDATE"
    EQUIVALENT_MANIFEST_TIEBREAK = "EQUIVALENT_MANIFEST_TIEBREAK"
    RECENCY_ONLY_TIEBREAK = "RECENCY_ONLY_TIEBREAK"
    OUTCOME_HISTORY_PREFERRED = "OUTCOME_HISTORY_PREFERRED"
    INSUFFICIENT_RANKING_EVIDENCE = "INSUFFICIENT_RANKING_EVIDENCE"


LOW_IMPACT_ENV_KEYS = frozenset({"WINEDLLOVERRIDES"})


@dataclass(frozen=True)
class RankingExplanation:
    profile_id: str
    profile_revision: int
    decisive_components: List[str]
    ranking_reason_code: RankingSelectionReasonCode
    was_tie_break: bool
    technical_superiority_established: bool
    active_reuse_eligible: bool
    ranking_components: Dict[str, float]
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "profile_revision": self.profile_revision,
            "decisive_components": list(self.decisive_components),
            "ranking_reason_code": self.ranking_reason_code.value,
            "was_tie_break": self.was_tie_break,
            "technical_superiority_established": self.technical_superiority_established,
            "active_reuse_eligible": self.active_reuse_eligible,
            "ranking_components": dict(self.ranking_components),
            "notes": self.notes,
        }


def _manifest_material_difference(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> bool:
    left_env = dict(left.get("environment") or {})
    right_env = dict(right.get("environment") or {})
    left_keys = set(left_env) - LOW_IMPACT_ENV_KEYS
    right_keys = set(right_env) - LOW_IMPACT_ENV_KEYS
    if left_keys != right_keys:
        return True
    for key in left_keys:
        if left_env.get(key) != right_env.get(key):
            return True
    for field in ("installed_components", "dll_overrides", "windows_version", "prefix_architecture"):
        if left.get(field) != right.get(field):
            if field == "environment":
                continue
            return True
    return False


def explain_ranking_selection(
    *,
    ranked_candidates: List[Any],
    profile_bundles: Mapping[str, Mapping[str, Any]],
    winner_profile_id: Optional[str],
    winner_revision: Optional[int],
) -> Optional[RankingExplanation]:
    """Classify why a winner was selected and whether active reuse is safe."""
    eligible = [
        c
        for c in ranked_candidates
        if getattr(c, "eligibility_status", None) == "eligible"
        and getattr(c, "ranking_status", None) == "ranked"
        and getattr(c, "final_rank_score", None) is not None
        and getattr(c, "winner_selectable", False)
    ]
    if not eligible or not winner_profile_id:
        return None

    if len(eligible) == 1:
        winner = eligible[0]
        return RankingExplanation(
            profile_id=winner_profile_id,
            profile_revision=int(winner_revision or winner.profile_revision),
            decisive_components=["single_eligible"],
            ranking_reason_code=RankingSelectionReasonCode.SINGLE_ELIGIBLE_CANDIDATE,
            was_tie_break=False,
            technical_superiority_established=True,
            active_reuse_eligible=True,
            ranking_components=dict(winner.ranking_components or {}),
            notes="Only one eligible winner-selectable candidate.",
        )

    sorted_eligible = sorted(eligible, key=lambda c: c.final_rank_score or 0.0, reverse=True)
    top = sorted_eligible[0]
    second = sorted_eligible[1]
    top_score = float(top.final_rank_score or 0.0)
    second_score = float(second.final_rank_score or 0.0)
    score_delta = round(top_score - second_score, 6)

    top_components = dict(top.ranking_components or {})
    second_components = dict(second.ranking_components or {})
    decisive: List[str] = []
    for key in sorted(set(top_components) | set(second_components)):
        delta = round(float(top_components.get(key, 0.0)) - float(second_components.get(key, 0.0)), 6)
        if abs(delta) >= 0.0001:
            decisive.append(key)

    top_bundle = profile_bundles.get(top.profile_id, {})
    second_bundle = profile_bundles.get(second.profile_id, {})
    top_manifest = (top_bundle.get("bridge") or {}).get("manifest_json")
    second_manifest = (second_bundle.get("bridge") or {}).get("manifest_json")
    if isinstance(top_manifest, str):
        import json

        top_manifest = json.loads(top_manifest)
    if isinstance(second_manifest, str):
        import json

        second_manifest = json.loads(second_manifest)

    material_diff = False
    if isinstance(top_manifest, dict) and isinstance(second_manifest, dict):
        material_diff = _manifest_material_difference(top_manifest, second_manifest)

    reuse_delta = float(top_components.get("reuse_success_rate", 0.5)) - float(
        second_components.get("reuse_success_rate", 0.5)
    )
    verification_delta = float(top_components.get("verification_confidence", 0.0)) - float(
        second_components.get("verification_confidence", 0.0)
    )
    failure_delta = float(second_components.get("failure_penalty", 0.0)) - float(
        top_components.get("failure_penalty", 0.0)
    )

    if reuse_delta > 0.05 or verification_delta > 0.05 or failure_delta > 0.05:
        reason = RankingSelectionReasonCode.OUTCOME_HISTORY_PREFERRED
        technical = True
        reuse_eligible = True
        notes = "Outcome-history or verification evidence preferred the winner."
    elif decisive == ["recency"] or (
        len(decisive) == 1 and decisive[0] == "recency" and score_delta < 0.01
    ):
        reason = RankingSelectionReasonCode.RECENCY_ONLY_TIEBREAK
        technical = False
        reuse_eligible = False
        notes = "Recency-only tie-break; does not establish technical superiority."
    elif not material_diff and score_delta < 0.01:
        reason = RankingSelectionReasonCode.EQUIVALENT_MANIFEST_TIEBREAK
        technical = False
        reuse_eligible = False
        notes = "Equivalent manifests; selection is deterministic tie-break only."
    elif material_diff:
        reason = RankingSelectionReasonCode.INSUFFICIENT_RANKING_EVIDENCE
        technical = False
        reuse_eligible = False
        notes = "Material manifest differences require outcome-history evidence for active reuse."
    else:
        reason = RankingSelectionReasonCode.RECENCY_ONLY_TIEBREAK
        technical = False
        reuse_eligible = False
        notes = "Winner not established by outcome-history evidence."

    return RankingExplanation(
        profile_id=winner_profile_id,
        profile_revision=int(winner_revision or top.profile_revision),
        decisive_components=decisive or ["recency"],
        ranking_reason_code=reason,
        was_tie_break=len(eligible) > 1 and score_delta < 0.01,
        technical_superiority_established=technical,
        active_reuse_eligible=reuse_eligible,
        ranking_components=top_components,
        notes=notes,
    )
