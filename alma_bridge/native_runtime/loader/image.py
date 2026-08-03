"""PE image mapping into memory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from alma_bridge.native_runtime.errors import LoadError, REASON_LOAD_FAILED
from alma_bridge.native_runtime.loader.memory import allocate_image
from alma_bridge.native_runtime.pe.parser import ParsedPE
from alma_bridge.native_runtime.pe.relocations import apply_relocations
from alma_bridge.native_runtime.pe.headers import IMAGE_DIRECTORY_ENTRY_BASERELOC


@dataclass
class LoadedImage:
    parsed: ParsedPE
    image: bytearray
    base_address: int
    entry_rva: int


def map_pe_image(parsed: ParsedPE) -> LoadedImage:
    try:
        size = parsed.optional.size_of_image
        image = bytearray(size)
        # Copy headers
        hdr_size = min(parsed.optional.size_of_headers, len(parsed.data))
        image[:hdr_size] = parsed.data[:hdr_size]
        # Copy sections
        for sec in parsed.sections:
            if sec.size_of_raw_data == 0:
                continue
            src = parsed.data[
                sec.pointer_to_raw_data : sec.pointer_to_raw_data + sec.size_of_raw_data
            ]
            dest_start = sec.virtual_address
            dest_end = dest_start + len(src)
            if dest_end <= len(image):
                image[dest_start:dest_end] = src
        base = parsed.optional.image_base
        mapped_base = base  # M1: load at preferred base in buffer (RVA space)
        delta = mapped_base - base
        reloc_rva = parsed.optional.data_directories[IMAGE_DIRECTORY_ENTRY_BASERELOC][0]
        reloc_size = parsed.optional.data_directories[IMAGE_DIRECTORY_ENTRY_BASERELOC][1]
        apply_relocations(
            image,
            parsed.sections,
            parsed.data,
            reloc_rva,
            reloc_size,
            delta=delta,
            is_pe32_plus=parsed.is_pe32_plus,
        )
        entry = parsed.optional.address_of_entry_point
        return LoadedImage(
            parsed=parsed,
            image=image,
            base_address=mapped_base,
            entry_rva=entry,
        )
    except Exception as exc:
        raise LoadError(str(exc), reason_codes=[REASON_LOAD_FAILED]) from exc
