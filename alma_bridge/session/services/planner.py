from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from alma_bridge.compatibility.planner import build_execution_plan
from alma_bridge.schemas.models import RuntimeKind


@dataclass
class ExecutionPlanStep:
    strategy_id: str
    runtime: str
    mode: str
    description: str
    command: List[str]
    env: Dict[str, str] = field(default_factory=dict)
    success_probability: Optional[float] = None
    historical_success_rate: Optional[float] = None
    rank_score: Optional[float] = None
    rank_source: Optional[str] = None
    rank_position: Optional[int] = None
    reranked_for_signature: Optional[str] = None


@dataclass
class ExecutionPlan:
    file_path: str
    steps: List[ExecutionPlanStep] = field(default_factory=list)

    @property
    def primary(self) -> Optional[ExecutionPlanStep]:
        return self.steps[0] if self.steps else None


class PlannerAdapterError(ValueError):
    """Raised when a legacy plan dict cannot be converted."""


def plan_from_legacy_dicts(file_path: str, plans: List[Dict[str, Any]]) -> ExecutionPlan:
    steps: List[ExecutionPlanStep] = []
    for raw in plans:
        if not isinstance(raw, dict):
            raise PlannerAdapterError("plan entry must be a dict")
        strategy_id = raw.get("strategy_id")
        runtime = raw.get("runtime")
        mode = raw.get("mode")
        command = raw.get("command")
        if not strategy_id or not runtime or not mode or not isinstance(command, list):
            raise PlannerAdapterError("plan dict missing required strategy/runtime/mode/command")
        steps.append(
            ExecutionPlanStep(
                strategy_id=str(strategy_id),
                runtime=str(runtime),
                mode=str(mode),
                description=str(raw.get("description") or strategy_id),
                command=[str(part) for part in command],
                env=dict(raw.get("env") or {}),
                success_probability=raw.get("success_probability"),
                historical_success_rate=raw.get("historical_success_rate"),
                rank_score=raw.get("rank_score"),
                rank_source=raw.get("rank_source"),
                rank_position=raw.get("rank_position"),
                reranked_for_signature=raw.get("reranked_for_signature"),
            )
        )
    return ExecutionPlan(file_path=file_path, steps=steps)


def plan_step_to_dict(step: ExecutionPlanStep) -> Dict[str, Any]:
    return {
        "strategy_id": step.strategy_id,
        "runtime": step.runtime,
        "mode": step.mode,
        "description": step.description,
        "command": step.command,
        "env": step.env,
        "success_probability": step.success_probability,
        "historical_success_rate": step.historical_success_rate,
        "rank_score": step.rank_score,
        "rank_source": step.rank_source,
        "rank_position": step.rank_position,
        "reranked_for_signature": step.reranked_for_signature,
    }


class CompatibilityPlanner(Protocol):
    def plan(
        self,
        file_path: str,
        *,
        runtime_hint: Optional[RuntimeKind] = None,
        preferred_strategy_id: Optional[str] = None,
        wine_prefix: Optional[str] = None,
        proton_path: Optional[str] = None,
        base_env: Optional[Dict[str, str]] = None,
        error_signature: Optional[str] = None,
    ) -> ExecutionPlan: ...


class DefaultCompatibilityPlanner:
    def plan(
        self,
        file_path: str,
        *,
        runtime_hint: Optional[RuntimeKind] = None,
        preferred_strategy_id: Optional[str] = None,
        wine_prefix: Optional[str] = None,
        proton_path: Optional[str] = None,
        base_env: Optional[Dict[str, str]] = None,
        error_signature: Optional[str] = None,
    ) -> ExecutionPlan:
        raw = build_execution_plan(
            file_path,
            runtime_hint=runtime_hint,
            preferred_strategy_id=preferred_strategy_id,
            wine_prefix=wine_prefix,
            proton_path=proton_path,
            base_env=base_env,
            error_signature=error_signature,
        )
        return plan_from_legacy_dicts(file_path, raw)
