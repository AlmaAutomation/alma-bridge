from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from alma_bridge.compatibility.strategies import Strategy, available_strategies, classify_binary
from alma_bridge.hardware.profiler import profile_hardware
from alma_bridge.learning.ranker import score_strategies
from alma_bridge.learning.training import load_ranker_artifact, load_ranker_metadata
from alma_bridge.schemas.models import RuntimeKind


def build_execution_plan(
    file_path: str,
    *,
    runtime_hint: Optional[RuntimeKind] = None,
    preferred_strategy_id: Optional[str] = None,
    wine_prefix: Optional[str] = None,
    proton_path: Optional[str] = None,
    base_env: Optional[Dict[str, str]] = None,
    error_signature: Optional[str] = None,
) -> List[Dict[str, Any]]:
    hardware = profile_hardware()
    capabilities = hardware["capabilities"]
    host_arch = hardware["architecture"]

    hint = runtime_hint.value if runtime_hint else None
    strategies = available_strategies(file_path, capabilities, host_arch, hint)
    scored = score_strategies(
        strategies,
        file_path=file_path,
        hardware_profile=hardware,
        preferred_strategy_id=preferred_strategy_id,
        error_signature=error_signature,
    )

    plans: List[Dict[str, Any]] = []
    for item in scored:
        strategy = item["strategy"]
        env = dict(base_env or {})
        if strategy.base_env:
            env.update(strategy.base_env)
        if wine_prefix and strategy.runtime in {"wine", "proton"}:
            env["WINEPREFIX"] = wine_prefix

        runtime_path = _resolve_runtime(strategy, hardware, proton_path)
        command = _build_command(strategy, file_path, runtime_path)

        plans.append(
            {
                "strategy_id": strategy.id,
                "runtime": strategy.runtime,
                "mode": strategy.mode,
                "description": strategy.description,
                "command": command,
                "env": env,
                "success_probability": item.get("success_probability"),
                "historical_success_rate": item.get("historical_success_rate"),
                "rank_score": item.get("rank_score"),
                "rank_source": item.get("rank_source"),
                "rank_position": item.get("rank_position"),
            }
        )
    return plans


def plan_ranker_summary() -> Dict[str, Any]:
    metadata = load_ranker_metadata()
    artifact = load_ranker_artifact()
    summary: Dict[str, Any] = {"model_loaded": artifact is not None}
    if metadata:
        summary["trained_at"] = metadata.get("trained_at")
        summary["records"] = metadata.get("records")
        summary["metrics"] = metadata.get("metrics")
    return summary


def _resolve_runtime(
    strategy: Strategy,
    hardware: Dict[str, Any],
    proton_path: Optional[str],
) -> Optional[str]:
    paths = hardware.get("paths", {})
    if strategy.runtime == "wine":
        return paths.get("wine")
    if strategy.runtime == "proton":
        return proton_path or paths.get("proton")
    if strategy.runtime == "qemu":
        return "qemu-x86_64"
    return None


def _build_command(
    strategy: Strategy,
    file_path: str,
    runtime_path: Optional[str],
) -> List[str]:
    path = str(Path(file_path).resolve())

    if strategy.runtime == "native":
        return [path]
    if strategy.runtime == "wine":
        return [runtime_path or "wine", path]
    if strategy.runtime == "proton":
        return [runtime_path or "proton", "run", path]
    if strategy.runtime == "qemu":
        return [runtime_path or "qemu-x86_64", path]
    if strategy.runtime == "container":
        from alma_bridge.execution.container_command import build_container_command

        host_arch = profile_hardware().get("architecture", "x86_64")
        binary_format = classify_binary(path, host_arch)
        return build_container_command(path, host_arch=host_arch, binary_format=binary_format)
    return [path]
