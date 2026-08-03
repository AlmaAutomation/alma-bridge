"""Read-only Compatibility Runtime HTTP routes."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from alma_bridge.native_runtime.eligibility import inspect_pe
from alma_bridge.native_runtime.models import PEInspection
from alma_bridge.runtime.models import ProviderInventoryEntry
from alma_bridge.runtime.registry import build_default_registry

router = APIRouter()
_registry = build_default_registry()


class NativeInspectRequest(BaseModel):
    file_path: str


@router.get(
    "/bridge/runtime/providers",
    response_model=List[ProviderInventoryEntry],
    tags=["Runtime"],
)
def runtime_providers() -> List[ProviderInventoryEntry]:
    """Read-only inventory of registered compatibility runtime providers."""
    return _registry.inventory()


@router.post(
    "/bridge/runtime/native/inspect",
    response_model=PEInspection,
    tags=["Runtime"],
)
def native_runtime_inspect(request: NativeInspectRequest) -> PEInspection:
    """Read-only PE eligibility inspection (no launch)."""
    from pathlib import Path

    path = Path(request.file_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {request.file_path}")
    return inspect_pe(request.file_path)
