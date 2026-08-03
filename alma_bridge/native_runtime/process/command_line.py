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
