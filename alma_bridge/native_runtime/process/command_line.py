"""Command-line simulation for native runtime fixtures."""

from __future__ import annotations

from typing import List


def build_command_line_w(args: List[str]) -> str:
    """Build a Windows-style command line from argv."""
    parts: List[str] = []
    for arg in args:
        if " " in arg or "\t" in arg:
            parts.append(f'"{arg}"')
        else:
            parts.append(arg)
    return " ".join(parts)


def build_command_line_utf16le(args: List[str]) -> bytes:
    """Build UTF-16LE command line bytes for native shim init."""
    return build_command_line_w(args).encode("utf-16-le") + b"\x00\x00"
