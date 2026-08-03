"""Sandboxed path resolution."""

from __future__ import annotations

from pathlib import Path


class PathViolationError(ValueError):
    pass


def resolve_workspace_path(workspace: Path, win_path: str) -> Path:
    """Resolve a Win32 path strictly under workspace."""
    cleaned = win_path.replace("\\", "/").lstrip("/")
    if ".." in cleaned.split("/"):
        raise PathViolationError("path traversal rejected")
    candidate = (workspace / cleaned).resolve()
    root = workspace.resolve()
    if not str(candidate).startswith(str(root)):
        raise PathViolationError("path outside workspace")
    return candidate
