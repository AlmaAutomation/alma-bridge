"""CompatibilityRuntimeProvider protocol."""

from __future__ import annotations

from typing import Dict, Optional, Protocol, runtime_checkable

from alma_bridge.runtime.capabilities import RuntimeCapabilities
from alma_bridge.runtime.models import (
    LaunchHandle,
    PrepareResult,
    RuntimeInspection,
    RuntimeObservation,
    TerminationResult,
)


@runtime_checkable
class CompatibilityRuntimeProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    @property
    def provider_version(self) -> str: ...

    def capabilities(self) -> RuntimeCapabilities: ...

    def inspect(
        self,
        file_path: str,
        *,
        env: Optional[Dict[str, str]] = None,
    ) -> RuntimeInspection: ...

    def prepare(
        self,
        file_path: str,
        *,
        command: Optional[list[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> PrepareResult: ...

    def launch(
        self,
        file_path: str,
        *,
        command: Optional[list[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> LaunchHandle: ...

    def observe(self, handle: LaunchHandle) -> RuntimeObservation: ...

    def terminate(self, handle: LaunchHandle) -> TerminationResult: ...

    def teardown(self, handle: LaunchHandle) -> None: ...
