"""PE import directory parsing."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Dict, List

from alma_bridge.native_runtime.pe.sections import SectionHeader, rva_to_offset


@dataclass
class ImportDescriptor:
    dll_name: str
    functions: List[str] = field(default_factory=list)


def parse_import_directory(
    data: bytes,
    sections: List[SectionHeader],
    import_rva: int,
    import_size: int,
    *,
    is_pe32_plus: bool,
) -> List[ImportDescriptor]:
    if import_rva == 0 or import_size == 0:
        return []
    offset = rva_to_offset(sections, import_rva)
    descriptors: List[ImportDescriptor] = []
    entry_size = 20
    pos = offset
    while True:
        if pos + entry_size > len(data):
            break
        oft, _tds, _fwd, name_rva, first_thunk = struct.unpack_from("<IIIII", data, pos)
        if all(v == 0 for v in (oft, _tds, _fwd, name_rva, first_thunk)):
            break
        if name_rva == 0:
            break
        name_off = rva_to_offset(sections, name_rva)
        dll_name = _read_cstring(data, name_off)
        thunk_rva = oft or first_thunk
        functions = _parse_thunk_names(data, sections, thunk_rva, is_pe32_plus=is_pe32_plus)
        descriptors.append(ImportDescriptor(dll_name=dll_name.lower(), functions=functions))
        pos += entry_size
    return descriptors


def import_dll_names(descriptors: List[ImportDescriptor]) -> List[str]:
    return sorted({d.dll_name for d in descriptors})


def _read_cstring(data: bytes, offset: int) -> str:
    end = data.find(b"\x00", offset)
    if end == -1:
        end = len(data)
    return data[offset:end].decode("ascii", errors="replace")


def _parse_thunk_names(
    data: bytes,
    sections: List[SectionHeader],
    thunk_rva: int,
    *,
    is_pe32_plus: bool,
) -> List[str]:
    if thunk_rva == 0:
        return []
    names: List[str] = []
    offset = rva_to_offset(sections, thunk_rva)
    thunk_size = 8 if is_pe32_plus else 4
    pos = offset
    while pos + thunk_size <= len(data):
        if is_pe32_plus:
            value = struct.unpack_from("<Q", data, pos)[0]
            ordinal_flag = 1 << 63
        else:
            value = struct.unpack_from("<I", data, pos)[0]
            ordinal_flag = 1 << 31
        if value == 0:
            break
        if value & ordinal_flag:
            names.append(f"ordinal_{value & 0xFFFF}")
        else:
            hint_name_off = rva_to_offset(sections, value)
            name = _read_cstring(data, hint_name_off + 2)
            names.append(name)
        pos += thunk_size
    return names


def parse_delay_import_directory(
    data: bytes,
    sections: List[SectionHeader],
    delay_rva: int,
    delay_size: int,
) -> List[str]:
    """Return DLL names from delay-load import directory (non-empty => reject)."""
    if delay_rva == 0 or delay_size == 0:
        return []
    offset = rva_to_offset(sections, delay_rva)
    dlls: List[str] = []
    pos = offset
    entry_size = 32
    while pos + entry_size <= len(data):
        fields = struct.unpack_from("<IIIIIIII", data, pos)
        if all(v == 0 for v in fields):
            break
        name_rva = fields[0]
        if name_rva:
            name_off = rva_to_offset(sections, name_rva)
            dlls.append(_read_cstring(data, name_off).lower())
        pos += entry_size
    return dlls
