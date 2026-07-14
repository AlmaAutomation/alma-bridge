from __future__ import annotations

import struct
from pathlib import Path


def write_minimal_pe(
    path: Path,
    *,
    subsystem: int = 2,
    pe32plus: bool = True,
) -> None:
    """Write a minimal PE stub with the requested Windows subsystem."""
    pe_offset = 0x80
    dos_stub = bytearray(pe_offset)
    dos_stub[0:2] = b"MZ"
    struct.pack_into("<I", dos_stub, 0x3C, pe_offset)

    coff_offset = pe_offset + 4
    optional_offset = coff_offset + 20
    headers = bytearray(optional_offset + 0xF0)
    headers[0:4] = b"PE\0\0"
    struct.pack_into("<H", headers, 4, 0x8664 if pe32plus else 0x14C)
    struct.pack_into("<H", headers, 6, 1)
    struct.pack_into("<H", headers, 20, 0xF0 if pe32plus else 0xE0)

    rel_optional = optional_offset - pe_offset
    struct.pack_into("<H", headers, rel_optional, 0x20B if pe32plus else 0x10B)
    struct.pack_into("<H", headers, rel_optional + 68, subsystem)

    section = bytearray(0x200)
    section[0:8] = b".text\0\0\0"

    blob = dos_stub + headers + section
    path.write_bytes(blob)
