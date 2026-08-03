"""PE section headers."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class SectionHeader:
    name: str
    virtual_size: int
    virtual_address: int
    size_of_raw_data: int
    pointer_to_raw_data: int
    pointer_to_relocations: int
    pointer_to_line_numbers: int
    number_of_relocations: int
    number_of_line_numbers: int
    characteristics: int


SECTION_FMT = "<8sIIIIIIHHI"


def read_section_headers(data: bytes, offset: int, count: int) -> List[SectionHeader]:
    sections: List[SectionHeader] = []
    pos = offset
    for _ in range(count):
        raw = struct.unpack_from(SECTION_FMT, data, pos)
        name = raw[0].split(b"\x00", 1)[0].decode("ascii", errors="replace")
        sections.append(
            SectionHeader(
                name=name,
                virtual_size=raw[1],
                virtual_address=raw[2],
                size_of_raw_data=raw[3],
                pointer_to_raw_data=raw[4],
                pointer_to_relocations=raw[5],
                pointer_to_line_numbers=raw[6],
                number_of_relocations=raw[7],
                number_of_line_numbers=raw[8],
                characteristics=raw[9],
            )
        )
        pos += struct.calcsize(SECTION_FMT)
    return sections


def rva_to_offset(sections: List[SectionHeader], rva: int) -> int:
    for sec in sections:
        size = max(sec.virtual_size, sec.size_of_raw_data)
        if sec.virtual_address <= rva < sec.virtual_address + size:
            return sec.pointer_to_raw_data + (rva - sec.virtual_address)
    raise ValueError(f"RVA {rva:#x} not in any section")
