from __future__ import annotations

from typing import Any, Dict, List, Optional

from alma_bridge.compatibility.strategies import STRATEGIES, Strategy, classify_binary
from alma_bridge.learning.installer import is_windows_installer
from alma_bridge.hardware.profiler import profile_hardware
from alma_bridge.learning.training import (
    load_ranker_artifact,
    load_ranker_metadata,
    predict_success_probability,
)
from alma_bridge.storage import outcomes


_STRATEGY_BY_ID = {strategy.id: strategy for strategy in STRATEGIES}


def score_strategies(
    strategies: List[Strategy],
    *,
    file_path: str,
    hardware_profile: Optional[Dict] = None,
    preferred_strategy_id: Optional[str] = None,
    error_signature: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Rank strategies and attach ML/historical scoring metadata for plan previews."""
    hardware = hardware_profile or profile_hardware()
    artifact = load_ranker_artifact()
    global_rates = outcomes.strategy_success_rates()
    historical_rates = (
        outcomes.strategy_success_rates_for_signature(error_signature)
        if error_signature
        else global_rates
    )
    binary_format = classify_binary(
        file_path,
        hardware.get("architecture", "x86_64"),
    )

    scored: List[Dict[str, Any]] = []
    if artifact and len(strategies) > 1:
        for strategy in strategies:
            probability = predict_success_probability(
                artifact,
                strategy_id=strategy.id,
                runtime=strategy.runtime,
                file_path=file_path,
                hardware_profile=hardware,
                error_signature=error_signature,
            )
            static = 1.0 / max(strategy.priority, 1)
            rank_score = (probability * 0.85) + (static * 0.15) + _format_boost(
                strategy, binary_format, file_path=file_path
            )
            scored.append(
                {
                    "strategy": strategy,
                    "success_probability": round(probability, 4),
                    "historical_success_rate": historical_rates.get(strategy.id),
                    "rank_score": round(rank_score, 4),
                    "rank_source": "ml",
                }
            )
    elif global_rates:
        rates = historical_rates
        for strategy in strategies:
            historical = rates.get(strategy.id, 0.0)
            static = 1.0 / max(strategy.priority, 1)
            rank_score = (historical * 0.8) + (static * 0.2) + _format_boost(
                strategy, binary_format, file_path=file_path
            )
            scored.append(
                {
                    "strategy": strategy,
                    "success_probability": None,
                    "historical_success_rate": round(historical, 4) if historical else None,
                    "rank_score": round(rank_score, 4),
                    "rank_source": "historical",
                }
            )
    else:
        for strategy in strategies:
            rank_score = 1.0 / max(strategy.priority, 1)
            scored.append(
                {
                    "strategy": strategy,
                    "success_probability": None,
                    "historical_success_rate": None,
                    "rank_score": round(rank_score, 4),
                    "rank_source": "static",
                }
            )

    scored.sort(key=lambda item: item["rank_score"], reverse=True)
    scored = _prioritize_scored(scored, preferred_strategy_id)
    for index, item in enumerate(scored, start=1):
        item["rank_position"] = index
    return scored


def rank_strategies(
    strategies: List[Strategy],
    *,
    file_path: str,
    hardware_profile: Optional[Dict] = None,
    preferred_strategy_id: Optional[str] = None,
    error_signature: Optional[str] = None,
) -> List[Strategy]:
    """Rank strategies using trained ML model, then historical rates, then static priority."""
    return [
        item["strategy"]
        for item in score_strategies(
            strategies,
            file_path=file_path,
            hardware_profile=hardware_profile,
            preferred_strategy_id=preferred_strategy_id,
            error_signature=error_signature,
        )
    ]


def rerank_plans(
    plans: List[Dict[str, Any]],
    *,
    file_path: str,
    hardware_profile: Dict[str, Any],
    error_signature: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Re-score remaining execution plans after a failed attempt."""
    if len(plans) <= 1:
        return plans

    strategies: List[Strategy] = []
    for plan in plans:
        strategy = _STRATEGY_BY_ID.get(plan.get("strategy_id", ""))
        if strategy:
            strategies.append(strategy)
    if len(strategies) <= 1:
        return plans

    scored = score_strategies(
        strategies,
        file_path=file_path,
        hardware_profile=hardware_profile,
        error_signature=error_signature,
    )
    by_id = {plan["strategy_id"]: plan for plan in plans}
    reranked: List[Dict[str, Any]] = []
    for item in scored:
        original = by_id.get(item["strategy"].id)
        if not original:
            continue
        updated = dict(original)
        updated["success_probability"] = item.get("success_probability")
        updated["historical_success_rate"] = item.get("historical_success_rate")
        updated["rank_score"] = item.get("rank_score")
        updated["rank_source"] = item.get("rank_source")
        updated["rank_position"] = item.get("rank_position")
        if error_signature:
            updated["reranked_for_signature"] = error_signature
        reranked.append(updated)

    seen = {plan["strategy_id"] for plan in reranked}
    for plan in plans:
        if plan["strategy_id"] not in seen:
            reranked.append(plan)
    return reranked


def _prioritize_scored(
    scored: List[Dict[str, Any]],
    preferred_strategy_id: Optional[str],
) -> List[Dict[str, Any]]:
    if not preferred_strategy_id:
        return scored
    preferred = [
        item for item in scored if item["strategy"].id == preferred_strategy_id
    ]
    if not preferred:
        return scored
    others = [
        item for item in scored if item["strategy"].id != preferred_strategy_id
    ]
    return preferred + others


def _format_boost(strategy: Strategy, binary_format: str, *, file_path: str = "") -> float:
    if binary_format == "pe" and is_windows_installer(file_path):
        if strategy.runtime == "wine":
            return 0.5
        if strategy.runtime == "proton":
            return 0.2
        if strategy.runtime == "container":
            return -0.3
    if binary_format == "pe":
        if strategy.runtime in {"wine", "proton"}:
            return 0.35
        if strategy.runtime == "container":
            return -0.25
    if binary_format in {"elf", "elf32", "appimage"}:
        if strategy.runtime == "native":
            return 0.35
        if strategy.runtime == "container":
            return -0.1
    if binary_format == "script" and strategy.runtime == "native":
        return 0.2
    return 0.0


def ranker_status() -> Dict[str, object]:
    metadata = load_ranker_metadata()
    artifact = load_ranker_artifact()
    return {
        "model_loaded": artifact is not None,
        "metadata": metadata,
    }
