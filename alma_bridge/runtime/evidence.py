"""Runtime evidence artifact helpers (read-only, non-authoritative)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from alma_bridge.runtime.models import (
    LaunchHandle,
    PrepareResult,
    RuntimeInspection,
    RuntimeObservation,
    TerminationResult,
)


def inspection_evidence(inspection: RuntimeInspection) -> Dict[str, Any]:
    return {
        "kind": "runtime_inspection",
        "provider_id": inspection.provider_id,
        "file_path": inspection.file_path,
        "binary_format": inspection.binary_format,
        "ready": inspection.ready,
        "notes": list(inspection.notes),
        "metadata": dict(inspection.metadata),
    }


def prepare_evidence(result: PrepareResult) -> Dict[str, Any]:
    return {
        "kind": "runtime_prepare",
        "provider_id": result.provider_id,
        "command": list(result.command),
        "env_keys": sorted(result.env.keys()),
        "ready": result.ready,
        "notes": list(result.notes),
    }


def launch_evidence(handle: LaunchHandle) -> Dict[str, Any]:
    return {
        "kind": "runtime_launch",
        "provider_id": handle.provider_id,
        "command": list(handle.command),
        "env_keys": sorted(handle.env.keys()),
        "launched": handle.launched,
        "pid": handle.pid,
    }


def observation_evidence(observation: RuntimeObservation) -> Dict[str, Any]:
    return {
        "kind": "runtime_observation",
        "provider_id": observation.provider_id,
        "running": observation.running,
        "exit_code": observation.exit_code,
        "notes": list(observation.notes),
    }


def termination_evidence(result: TerminationResult) -> Dict[str, Any]:
    return {
        "kind": "runtime_termination",
        "provider_id": result.provider_id,
        "terminated": result.terminated,
        "exit_code": result.exit_code,
        "notes": list(result.notes),
    }


def bundle_runtime_evidence(
    *,
    inspection: Optional[RuntimeInspection] = None,
    prepare: Optional[PrepareResult] = None,
    launch: Optional[LaunchHandle] = None,
    observation: Optional[RuntimeObservation] = None,
    termination: Optional[TerminationResult] = None,
) -> List[Dict[str, Any]]:
    artifacts: List[Dict[str, Any]] = []
    if inspection is not None:
        artifacts.append(inspection_evidence(inspection))
    if prepare is not None:
        artifacts.append(prepare_evidence(prepare))
    if launch is not None:
        artifacts.append(launch_evidence(launch))
    if observation is not None:
        artifacts.append(observation_evidence(observation))
    if termination is not None:
        artifacts.append(termination_evidence(termination))
    return artifacts
