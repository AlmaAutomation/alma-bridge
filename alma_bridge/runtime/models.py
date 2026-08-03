"""Compatibility runtime domain models."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from alma_bridge.runtime.capabilities import CapabilityState


class RuntimePhase(str, Enum):
    INSPECT = "inspect"
    PREPARE = "prepare"
    LAUNCH = "launch"
    OBSERVE = "observe"
    TERMINATE = "terminate"
    TEARDOWN = "teardown"


class RuntimeRequirements(BaseModel):
    """Capability requirements for provider selection."""

    required: List[str] = Field(default_factory=list)
    preferred: List[str] = Field(default_factory=list)
    binary_format: Optional[str] = None
    strategy_id: Optional[str] = None

    def minimum_state(self, capability: str) -> CapabilityState:
        if capability in self.required:
            return CapabilityState.SUPPORTED
        if capability in self.preferred:
            return CapabilityState.PARTIAL
        return CapabilityState.UNKNOWN


class RuntimeInspection(BaseModel):
    provider_id: str
    file_path: str
    binary_format: Optional[str] = None
    ready: bool = False
    notes: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PrepareResult(BaseModel):
    provider_id: str
    command: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    ready: bool = False
    notes: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LaunchHandle(BaseModel):
    provider_id: str
    command: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    pid: Optional[int] = None
    launched: bool = False
    file_path: Optional[str] = None
    handle_token: Optional[str] = None


class RuntimeObservation(BaseModel):
    provider_id: str
    running: bool = False
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    notes: List[str] = Field(default_factory=list)


class TerminationResult(BaseModel):
    provider_id: str
    terminated: bool = False
    exit_code: Optional[int] = None
    notes: List[str] = Field(default_factory=list)


class ProviderInventoryEntry(BaseModel):
    provider_id: str
    provider_version: str
    capabilities: Dict[str, str]
    experimental: bool = False
