"""Sandboxed file operations for native runtime."""

from __future__ import annotations

from pathlib import Path

from alma_bridge.native_runtime.filesystem.paths import PathViolationError, resolve_workspace_path


def read_file(workspace: Path, win_path: str) -> bytes:
    path = resolve_workspace_path(workspace, win_path)
    if not path.is_file():
        raise FileNotFoundError(win_path)
    return path.read_bytes()


def write_file(workspace: Path, win_path: str, data: bytes) -> None:
    path = resolve_workspace_path(workspace, win_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
