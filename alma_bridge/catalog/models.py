"""Domain models for the Compatibility Application Catalog."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

CATALOG_SCHEMA_VERSION = "compatibility_catalog_v1"
CATALOG_ENGINE_VERSION = "compatibility_catalog_aggregation_v1"


class CatalogApplicationEntry(BaseModel):
    fingerprint: str
    name: str
    total_sessions: int = Field(ge=0)
    verified_successes: int = Field(ge=0)
    verified_failures: int = Field(ge=0)
    latest_status: str
    latest_session: str
    last_regression_change: Optional[str] = None
    observed_frameworks: List[str] = Field(default_factory=list)
    observed_strategies: List[str] = Field(default_factory=list)
    latest_environment_summary: Optional[str] = None

    @field_validator("observed_frameworks", "observed_strategies")
    @classmethod
    def _sort_labels(cls, value: List[str]) -> List[str]:
        return sorted(value)


class CompatibilityCatalogResponse(BaseModel):
    schema_version: str = CATALOG_SCHEMA_VERSION
    engine_version: str = CATALOG_ENGINE_VERSION
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    applications: List[CatalogApplicationEntry] = Field(default_factory=list)

    @field_validator("applications")
    @classmethod
    def _sort_applications(cls, value: List[CatalogApplicationEntry]) -> List[CatalogApplicationEntry]:
        return sorted(value, key=lambda item: (item.name.lower(), item.fingerprint))


class CatalogNotFoundError(Exception):
    """Raised when no catalog entries exist."""
