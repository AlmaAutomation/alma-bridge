"""Native runtime domain models."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PEInspection(BaseModel):
    """Read-only PE inspection result."""

    file_path: str
    eligible: bool = False
    machine: Optional[str] = None
    subsystem: Optional[str] = None
    import_dlls: List[str] = Field(default_factory=list)
    reason_codes: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NativeRunResult(BaseModel):
    """Result from worker subprocess execution."""

    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    success: bool = False
    error: Optional[str] = None
    reason_codes: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
