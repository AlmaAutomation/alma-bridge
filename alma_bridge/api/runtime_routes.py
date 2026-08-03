"""Read-only Compatibility Runtime HTTP routes."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter

from alma_bridge.runtime.models import ProviderInventoryEntry
from alma_bridge.runtime.registry import build_default_registry

router = APIRouter()
_registry = build_default_registry()


@router.get(
    "/bridge/runtime/providers",
    response_model=List[ProviderInventoryEntry],
    tags=["Runtime"],
)
def runtime_providers() -> List[ProviderInventoryEntry]:
    """Read-only inventory of registered compatibility runtime providers."""
    return _registry.inventory()
