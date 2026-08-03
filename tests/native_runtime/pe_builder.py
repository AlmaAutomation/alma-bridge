"""Synthetic minimal PE builders for unit tests."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import List, Optional, Tuple


def build_minimal_pe64(
    *,
    subsystem: int = 3,
    imports: Optional[List[Tuple[str, List[str]]]] = None,
    tls: bool = False,
    cli: bool = False,
) -> bytes:
    """Build a minimal PE32+ stub sufficient for parser/eligibility tests."""
    imports = imports or [("kernel32.dll", ["ExitProcess"])]
    dos = bytearray(128)
    struct.pack_into("<H", dos, 0, 0x5A4D)
    pe_off = 128
    struct.pack_into("<I", dos, 60, pe_off)

    coff = struct.pack(
        "<HHIIIHH",
        0x8664,
        1,
        0,
        0,
        0,
        240,
        0x22,
    )
    # Optional header PE32+
    opt = bytearray(240)
    struct.pack_into("<H", opt, 0, 0x20B)
    struct.pack_into("<I", opt, 16, 0x1000)  # entry
    struct.pack_into("<Q", opt, 24, 0x140000000)  # image base
    struct.pack_into("<I", opt, 56, 0x3000)  # size of image
    struct.pack_into("<I", opt, 60, 0x200)  # headers size
    struct.pack_into("<H", opt, 68, subsystem)
    struct.pack_into("<I", opt, 108, 16)  # number of rva and sizes

    # One .text section
    sec = struct.pack(
        "<8sIIIIIIHHI",
        b".text\x00\x00\x00",
        0x200,
        0x1000,
        0x200,
        0x200,
        0,
        0,
        0,
        0,
        0x60000020,
    )

    headers = dos + b"PE\x00\x00" + coff + opt + sec
    headers = headers.ljust(0x200, b"\x00")

    text = b"\x90" * 0x200  # NOP fill

    # Import tables appended after headers+text
    imp_blob = _build_import_blob(imports, base_rva=0x2000)
    cli_blob = b""
    if cli:
        struct.pack_into("<I", opt, 68 + 2 + 2 + 4 * 8 + 14 * 8, 0x4000)  # rough; tests use parser fields
    data = headers + text + imp_blob
    return bytes(data)


def _build_import_blob(imports: List[Tuple[str, List[str]]], *, base_rva: int) -> bytes:
    # Simplified: append DLL names only for import parser smoke tests
    blob = bytearray()
    for dll, _funcs in imports:
        blob.extend(dll.encode("ascii") + b"\x00")
    return bytes(blob)


def write_pe(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path
