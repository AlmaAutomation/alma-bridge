"""Extended PE binary analyzer — reuses native_runtime PE parser."""

from __future__ import annotations

import hashlib
import struct
from typing import List, Tuple

from alma_bridge.compatibility_intelligence.imports import detect_forwarded_imports
from alma_bridge.compatibility_intelligence.models import PeAnalysisMetadata, SectionSummary
from alma_bridge.native_runtime.pe.headers import (
    IMAGE_DIRECTORY_ENTRY_BASERELOC,
    machine_name,
    subsystem_name,
)
from alma_bridge.native_runtime.pe.parser import ParsedPE, parse_pe_file
from alma_bridge.native_runtime.pe.sections import rva_to_offset

# Standard PE data directory indices
_DIR_EXPORT = 0
_DIR_RESOURCE = 2
_DIR_EXCEPTION = 3
_DIR_DEBUG = 6
_DIR_LOAD_CONFIG = 10
_DIR_CLR = 14

# Section characteristic flags
_SCN_CNT_CODE = 0x00000020
_SCN_CNT_INITIALIZED_DATA = 0x00000040
_SCN_CNT_UNINITIALIZED_DATA = 0x00000080
_SCN_MEM_EXECUTE = 0x20000000
_SCN_MEM_READ = 0x40000000
_SCN_MEM_WRITE = 0x80000000


def binary_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _dir_rva_size(optional, index: int) -> Tuple[int, int]:
    if index >= len(optional.data_directories):
        return 0, 0
    return optional.data_directories[index]


def _section_flags(characteristics: int) -> List[str]:
    flags: List[str] = []
    if characteristics & _SCN_CNT_CODE:
        flags.append("code")
    if characteristics & _SCN_CNT_INITIALIZED_DATA:
        flags.append("initialized_data")
    if characteristics & _SCN_CNT_UNINITIALIZED_DATA:
        flags.append("uninitialized_data")
    if characteristics & _SCN_MEM_EXECUTE:
        flags.append("executable")
    if characteristics & _SCN_MEM_READ:
        flags.append("readable")
    if characteristics & _SCN_MEM_WRITE:
        flags.append("writable")
    return flags


def _parse_exports(data: bytes, sections, export_rva: int, export_size: int) -> Tuple[int, List[str]]:
    if export_rva == 0 or export_size == 0:
        return 0, []
    try:
        offset = rva_to_offset(sections, export_rva)
    except (ValueError, IndexError):
        return 0, []
    if offset + 40 > len(data):
        return 0, []
    num_functions, num_names, _addr_table, _name_ptrs, _ordinals = struct.unpack_from(
        "<IIIII", data, offset + 16
    )
    forwarded: List[str] = []
    addr_table_rva = struct.unpack_from("<I", data, offset + 28)[0]
    if addr_table_rva and num_functions:
        try:
            table_off = rva_to_offset(sections, addr_table_rva)
            for i in range(min(num_functions, 256)):
                fn_rva = struct.unpack_from("<I", data, table_off + i * 4)[0]
                if export_rva <= fn_rva < export_rva + export_size:
                    try:
                        fwd_off = rva_to_offset(sections, fn_rva)
                        end = data.find(b"\x00", fwd_off)
                        if end != -1:
                            fwd = data[fwd_off:end].decode("ascii", errors="replace")
                            if "." in fwd:
                                forwarded.append(fwd)
                    except (ValueError, IndexError):
                        pass
        except (ValueError, IndexError):
            pass
    return num_names or num_functions, sorted(forwarded)


def _has_resource_type(data: bytes, sections, resource_rva: int, resource_size: int, type_id: int) -> bool:
    if resource_rva == 0 or resource_size == 0:
        return False
    try:
        offset = rva_to_offset(sections, resource_rva)
    except (ValueError, IndexError):
        return False
    if offset + 16 > len(data):
        return False
    num_named, num_id = struct.unpack_from("<II", data, offset)
    pos = offset + 16
    for _ in range(num_named + num_id):
        if pos + 8 > len(data):
            break
        name_or_id, _offset_to_data = struct.unpack_from("<II", data, pos)
        pos += 8
        if name_or_id == type_id:
            return True
    return False


def analyze_pe(file_path: str) -> Tuple[ParsedPE, PeAnalysisMetadata, str]:
    """Parse PE and extract extended metadata (read-only, no execution)."""
    parsed = parse_pe_file(file_path)
    data = parsed.data
    optional = parsed.optional
    sections = parsed.sections

    export_rva, export_size = _dir_rva_size(optional, _DIR_EXPORT)
    export_count, forwarded_exports = _parse_exports(data, sections, export_rva, export_size)

    reloc_rva, reloc_size = _dir_rva_size(optional, IMAGE_DIRECTORY_ENTRY_BASERELOC)
    resource_rva, resource_size = _dir_rva_size(optional, _DIR_RESOURCE)
    debug_rva, _ = _dir_rva_size(optional, _DIR_DEBUG)
    load_cfg_rva, _ = _dir_rva_size(optional, _DIR_LOAD_CONFIG)
    exc_rva, _ = _dir_rva_size(optional, _DIR_EXCEPTION)

    resource_types: List[str] = []
    if resource_rva:
        resource_types.append("resource_directory")
    if _has_resource_type(data, sections, resource_rva, resource_size, 24):
        resource_types.append("manifest")

    section_summaries = [
        SectionSummary(
            name=sec.name,
            virtual_size=sec.virtual_size,
            raw_size=sec.size_of_raw_data,
            characteristics=sec.characteristics,
            flags=_section_flags(sec.characteristics),
        )
        for sec in sections
    ]

    forwarded_imports = detect_forwarded_imports(parsed.imports)

    metadata = PeAnalysisMetadata(
        architecture=machine_name(parsed.coff.machine),
        subsystem=subsystem_name(optional.subsystem),
        entry_point_rva=optional.address_of_entry_point,
        image_size=optional.size_of_image,
        is_pe32_plus=parsed.is_pe32_plus,
        has_tls=parsed.has_tls,
        has_relocations=reloc_rva != 0 and reloc_size != 0,
        has_clr=parsed.cli_rva != 0,
        has_manifest="manifest" in resource_types,
        has_debug=debug_rva != 0,
        has_load_config=load_cfg_rva != 0,
        has_exception_directory=exc_rva != 0,
        export_count=export_count,
        forwarded_exports=forwarded_exports,
        sections=section_summaries,
        delay_import_dlls=sorted(parsed.delay_import_dlls),
        forwarded_imports=forwarded_imports,
        resource_types=sorted(resource_types),
    )
    digest = binary_digest(data)
    return parsed, metadata, digest
