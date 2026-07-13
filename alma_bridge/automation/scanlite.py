"""Lightweight local directory scan for automation (no alma-core dependency)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List


def scan_lite(path: str, *, max_files: int = 5000, max_depth: int = 4) -> Dict[str, Any]:
    """Fast recursive scan: file counts, ELF/PE hints, top-level summary."""
    root = Path(path).expanduser()
    if not root.exists():
        return {"path": str(root), "ok": False, "error": "path not found"}

    files = 0
    dirs = 0
    elf = 0
    pe = 0
    samples: List[str] = []

    def walk(current: Path, depth: int) -> None:
        nonlocal files, dirs, elf, pe
        if depth > max_depth or files >= max_files:
            return
        try:
            entries = list(current.iterdir())
        except OSError:
            return
        for entry in entries:
            if files >= max_files:
                break
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir():
                    dirs += 1
                    walk(entry, depth + 1)
                elif entry.is_file():
                    files += 1
                    if len(samples) < 20:
                        samples.append(str(entry))
                    try:
                        with open(entry, "rb") as handle:
                            magic = handle.read(4)
                        if magic[:4] == b"\x7fELF":
                            elf += 1
                        elif magic[:2] == b"MZ":
                            pe += 1
                    except OSError:
                        pass
            except OSError:
                continue

    walk(root, 0)
    return {
        "path": str(root),
        "ok": True,
        "files_scanned": files,
        "dirs_seen": dirs,
        "elf_binaries": elf,
        "pe_binaries": pe,
        "truncated": files >= max_files,
        "sample_paths": samples,
    }
