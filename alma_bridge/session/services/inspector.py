from __future__ import annotations

from typing import Any, Dict, Optional, Protocol

from alma_bridge.bridge.profile_builder import build_compatibility_inspection
from alma_bridge.schemas.bridge_domain import CompatibilityInspection


class CompatibilityInspector(Protocol):
    def inspect(
        self,
        file_path: str,
        *,
        wine_prefix: Optional[str] = None,
        scanner_data: Optional[Dict[str, Any]] = None,
    ) -> CompatibilityInspection: ...


class DefaultCompatibilityInspector:
    def inspect(
        self,
        file_path: str,
        *,
        wine_prefix: Optional[str] = None,
        scanner_data: Optional[Dict[str, Any]] = None,
    ) -> CompatibilityInspection:
        return build_compatibility_inspection(
            file_path,
            scanner_data=scanner_data,
            wine_prefix=wine_prefix,
        )
