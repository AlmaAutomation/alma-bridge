"""Bridge between compatibility planner and runtime provider selection."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from alma_bridge.compatibility.planner import build_execution_plan
from alma_bridge.compatibility_intelligence.planner_integration import (
    annotate_plans_with_capability_analysis,
)
from alma_bridge.runtime.registry import RuntimeRegistry, build_default_registry
from alma_bridge.runtime.selection import (
    provider_id_for_strategy,
    requirements_for_strategy,
    select_provider_for_strategy,
)
from alma_bridge.schemas.models import RuntimeKind


def annotate_plan_with_runtime_providers(
    plans: List[Dict[str, Any]],
    registry: Optional[RuntimeRegistry] = None,
) -> List[Dict[str, Any]]:
    """Add runtime_provider_id to plan dicts without changing strategy IDs."""
    reg = registry or build_default_registry()
    annotated: List[Dict[str, Any]] = []
    for plan in plans:
        enriched = dict(plan)
        strategy_id = str(plan.get("strategy_id") or "")
        provider_id = provider_id_for_strategy(strategy_id)
        if provider_id:
            provider = select_provider_for_strategy(strategy_id, reg)
            enriched["runtime_provider_id"] = provider_id
            enriched["runtime_provider_ready"] = provider is not None
        else:
            enriched["runtime_provider_id"] = None
            enriched["runtime_provider_ready"] = None
        annotated.append(enriched)
    return annotated


def build_execution_plan_with_runtime(
    file_path: str,
    *,
    runtime_hint: Optional[RuntimeKind] = None,
    preferred_strategy_id: Optional[str] = None,
    wine_prefix: Optional[str] = None,
    proton_path: Optional[str] = None,
    base_env: Optional[Dict[str, str]] = None,
    error_signature: Optional[str] = None,
    registry: Optional[RuntimeRegistry] = None,
) -> List[Dict[str, Any]]:
    """Build execution plan and annotate with runtime provider metadata (additive)."""
    plans = build_execution_plan(
        file_path,
        runtime_hint=runtime_hint,
        preferred_strategy_id=preferred_strategy_id,
        wine_prefix=wine_prefix,
        proton_path=proton_path,
        base_env=base_env,
        error_signature=error_signature,
    )
    plans = annotate_plan_with_runtime_providers(plans, registry=registry)
    return annotate_plans_with_capability_analysis(plans, file_path, registry=registry)


def runtime_requirements_for_plan(plan: Dict[str, Any]) -> Optional[dict]:
    strategy_id = plan.get("strategy_id")
    if not strategy_id:
        return None
    req = requirements_for_strategy(str(strategy_id))
    return req.model_dump()
