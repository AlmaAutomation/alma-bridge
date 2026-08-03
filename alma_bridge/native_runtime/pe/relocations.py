"""PE base relocation parsing and application."""

from __future__ import annotations

import struct
from typing import List

from alma_bridge.native_runtime.pe.headers import (
    IMAGE_REL_BASED_ABSOLUTE,
    IMAGE_REL_BASED_DIR64,
    IMAGE_REL_BASED_HIGHLOW,
)
from alma_bridge.native_runtime.pe.sections import SectionHeader, rva_to_offset


def has_relocations(sections: List[SectionHeader], reloc_rva: int, reloc_size: int) -> bool:
    return reloc_rva != 0 and reloc_size != 0


def apply_relocations(
    image: bytearray,
    sections: List[SectionHeader],
    file_data: bytes,
    reloc_rva: int,
    reloc_size: int,
    *,
    delta: int,
    is_pe32_plus: bool,
) -> None:
    if delta == 0 or reloc_rva == 0:
        return
    offset = rva_to_offset(sections, reloc_rva)
    end = offset + reloc_size
    pos = offset
    while pos < end:
        page_rva, block_size = struct.unpack_from("<II", file_data, pos)
        if block_size == 0:
            break
        pos += 8
        block_end = pos + block_size - 8
        while pos < block_end:
            entry = struct.unpack_from("<H", file_data, pos)[0]
            pos += 2
            reloc_type = entry >> 12
            reloc_offset = entry & 0xFFF
            target_rva = page_rva + reloc_offset
            if reloc_type == IMAGE_REL_BASED_ABSOLUTE:
                continue
            target_off = _rva_to_image_offset(sections, target_rva)
            if reloc_type == IMAGE_REL_BASED_DIR64 and is_pe32_plus:
                value = struct.unpack_from("<Q", image, target_off)[0]
                struct.pack_into("<Q", image, target_off, (value + delta) & 0xFFFFFFFFFFFFFFFF)
            elif reloc_type == IMAGE_REL_BASED_HIGHLOW:
                value = struct.unpack_from("<I", image, target_off)[0]
                struct.pack_into("<I", image, target_off, (value + delta) & 0xFFFFFFFF)
            else:
                raise ValueError(f"unsupported relocation type {reloc_type}")
        pos = offset + block_size
        offset = pos


def _rva_to_image_offset(sections: List[SectionHeader], rva: int) -> int:
    for sec in sections:
        size = max(sec.virtual_size, sec.size_of_raw_data)
        if sec.virtual_address <= rva < sec.virtual_address + size:
            return sec.virtual_address + (rva - sec.virtual_address)
    raise ValueError(f"RVA {rva:#x} not mapped")
