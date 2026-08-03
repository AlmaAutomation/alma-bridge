"""Experimental native Alma runtime provider (fail-closed)."""

from __future__ import annotations

from typing import Dict, List, Optional

from alma_bridge.runtime.capabilities import CapabilityState, PE_CONSOLE, RuntimeCapabilities
from alma_bridge.runtime.errors import RuntimeNotSupportedError
from alma_bridge.runtime.models import (
    LaunchHandle,
    PrepareResult,
    RuntimeInspection,
    RuntimeObservation,
    TerminationResult,
)

_PROVIDER_VERSION = "0.0.0-experimental"


class NativeAlmaRuntime:
    """Experimental fail-closed provider with minimal console PE declarations only."""

    @property
    def provider_id(self) -> str:
        return "native_alma"

    @property
    def provider_version(self) -> str:
        return _PROVIDER_VERSION

    def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities.from_states(
            **{
                PE_CONSOLE: CapabilityState.UNKNOWN,
            }
        )

    def inspect(
        self,
        file_path: str,
        *,
        env: Optional[Dict[str, str]] = None,
    ) -> RuntimeInspection:
        return RuntimeInspection(
            provider_id=self.provider_id,
            file_path=file_path,
            ready=False,
            notes=["Native Alma runtime is experimental and fail-closed in Phase 0B"],
        )

    def prepare(
        self,
        file_path: str,
        *,
        command: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> PrepareResult:
        raise RuntimeNotSupportedError(
            "Native Alma runtime is not available; see docs/roadmap/native-alma-runtime.md"
        )

    def launch(
        self,
        file_path: str,
        *,
        command: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> LaunchHandle:
        raise RuntimeNotSupportedError(
            "Native Alma runtime is not available; see docs/roadmap/native-alma-runtime.md"
        )

    def observe(self, handle: LaunchHandle) -> RuntimeObservation:
        raise RuntimeNotSupportedError("Native Alma runtime is not available")

    def terminate(self, handle: LaunchHandle) -> TerminationResult:
        raise RuntimeNotSupportedError("Native Alma runtime is not available")

    def teardown(self, handle: LaunchHandle) -> None:
        raise RuntimeNotSupportedError("Native Alma runtime is not available")
