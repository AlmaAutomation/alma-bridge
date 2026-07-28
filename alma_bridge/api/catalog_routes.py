"""Read-only Compatibility Catalog HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from alma_bridge.catalog.models import CatalogNotFoundError, CompatibilityCatalogResponse
from alma_bridge.catalog.service import CompatibilityCatalogService

router = APIRouter()
_service = CompatibilityCatalogService()


@router.get(
    "/bridge/catalog/applications",
    response_model=CompatibilityCatalogResponse,
    tags=["Catalog"],
)
def catalog_applications() -> CompatibilityCatalogResponse:
    try:
        return _service.list_applications()
    except CatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
