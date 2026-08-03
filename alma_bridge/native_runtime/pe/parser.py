"""PE file parser."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from alma_bridge.native_runtime.errors import PEParseError
from alma_bridge.native_runtime.pe.headers import (
    IMAGE_DIRECTORY_ENTRY_BASERELOC,
    IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT,
    IMAGE_DIRECTORY_ENTRY_IMPORT,
    IMAGE_DIRECTORY_ENTRY_TLS,
    IMAGE_NT_OPTIONAL_HDR32_MAGIC,
    IMAGE_NT_OPTIONAL_HDR64_MAGIC,
    IMAGE_NT_SIGNATURE,
    OptionalHeader,
    read_coff_header,
    read_dos_header,
)
from alma_bridge.native_runtime.pe.imports import (
    ImportDescriptor,
    parse_delay_import_directory,
    parse_import_directory,
)
from alma_bridge.native_runtime.pe.sections import SectionHeader, read_section_headers


@dataclass
class ParsedPE:
    file_path: str
    data: bytes
    is_pe32_plus: bool
    coff: object
    optional: OptionalHeader
    sections: List[SectionHeader] = field(default_factory=list)
    imports: List[ImportDescriptor] = field(default_factory=list)
    delay_import_dlls: List[str] = field(default_factory=list)
    has_tls: bool = False
    cli_rva: int = 0

    @property
    def import_dlls(self) -> List[str]:
        return sorted({imp.dll_name for imp in self.imports})


def parse_pe_file(file_path: str | Path) -> ParsedPE:
    path = Path(file_path)
    if not path.is_file():
        raise PEParseError(f"file not found: {path}", reason_codes=["not_pe"])
    data = path.read_bytes()
    return parse_pe_bytes(str(path), data)


def parse_pe_bytes(file_path: str, data: bytes) -> ParsedPE:
    try:
        dos = read_dos_header(data)
        pe_off = dos.e_lfanew
        if pe_off + 4 > len(data):
            raise ValueError("truncated PE signature")
        signature = struct.unpack_from("<I", data, pe_off)[0]
        if signature != IMAGE_NT_SIGNATURE:
            raise ValueError(f"invalid PE signature: {signature:#x}")
        coff = read_coff_header(data, pe_off + 4)
        opt_off = pe_off + 4 + 20
        optional, is_pe32_plus = _read_optional_header(data, opt_off, coff.size_of_optional_header)
        sec_off = opt_off + coff.size_of_optional_header
        sections = read_section_headers(data, sec_off, coff.number_of_sections)
        imports = parse_import_directory(
            data,
            sections,
            _dir_rva(optional, IMAGE_DIRECTORY_ENTRY_IMPORT),
            _dir_size(optional, IMAGE_DIRECTORY_ENTRY_IMPORT),
            is_pe32_plus=is_pe32_plus,
        )
        delay_dlls = parse_delay_import_directory(
            data,
            sections,
            _dir_rva(optional, IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT),
            _dir_size(optional, IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT),
        )
        tls_rva = _dir_rva(optional, IMAGE_DIRECTORY_ENTRY_TLS)
        has_tls = tls_rva != 0
        cli_rva = _dir_rva(optional, 14)  # COM descriptor / .NET
        return ParsedPE(
            file_path=file_path,
            data=data,
            is_pe32_plus=is_pe32_plus,
            coff=coff,
            optional=optional,
            sections=sections,
            imports=imports,
            delay_import_dlls=delay_dlls,
            has_tls=has_tls,
            cli_rva=cli_rva,
        )
    except PEParseError:
        raise
    except Exception as exc:
        raise PEParseError(str(exc), reason_codes=["invalid_pe"]) from exc


def _dir_rva(optional: OptionalHeader, index: int) -> int:
    if index >= len(optional.data_directories):
        return 0
    return optional.data_directories[index][0]


def _dir_size(optional: OptionalHeader, index: int) -> int:
    if index >= len(optional.data_directories):
        return 0
    return optional.data_directories[index][1]


def _read_optional_header(data: bytes, offset: int, size: int) -> tuple[OptionalHeader, bool]:
    magic = struct.unpack_from("<H", data, offset)[0]
    if magic == IMAGE_NT_OPTIONAL_HDR64_MAGIC:
        return _read_optional64(data, offset), True
    if magic == IMAGE_NT_OPTIONAL_HDR32_MAGIC:
        return _read_optional32(data, offset), False
    raise ValueError(f"unknown optional header magic: {magic:#x}")


def _read_optional32(data: bytes, offset: int) -> OptionalHeader:
    fmt = "<HBBIIIIIIIHHHHHHIIIIHHIIIIIIII"
    f = struct.unpack_from(fmt, data, offset)
    num_dirs = f[29]
    dir_off = offset + struct.calcsize(fmt)
    directories = _read_data_directories(data, dir_off, num_dirs)
    return OptionalHeader(
        magic=f[0],
        major_linker_version=f[1],
        minor_linker_version=f[2],
        size_of_code=f[3],
        size_of_initialized_data=f[4],
        size_of_uninitialized_data=f[5],
        address_of_entry_point=f[6],
        base_of_code=f[7],
        image_base=f[9],
        section_alignment=f[10],
        file_alignment=f[11],
        major_os_version=f[12],
        minor_os_version=f[13],
        major_image_version=f[14],
        minor_image_version=f[15],
        major_subsystem_version=f[16],
        minor_subsystem_version=f[17],
        win32_version_value=f[18],
        size_of_image=f[19],
        size_of_headers=f[20],
        checksum=f[21],
        subsystem=f[22],
        dll_characteristics=f[23],
        size_of_stack_reserve=f[24],
        size_of_stack_commit=f[25],
        size_of_heap_reserve=f[26],
        size_of_heap_commit=f[27],
        loader_flags=f[28],
        number_of_rva_and_sizes=f[29],
        data_directories=directories,
        base_of_data=f[8],
    )


def _read_optional64(data: bytes, offset: int) -> OptionalHeader:
    fmt = "<HBBIIIIIQIIHHHHHHIIIIHHQQQQII"
    f = struct.unpack_from(fmt, data, offset)
    num_dirs = f[28]
    dir_off = offset + struct.calcsize(fmt)
    directories = _read_data_directories(data, dir_off, num_dirs)
    return OptionalHeader(
        magic=f[0],
        major_linker_version=f[1],
        minor_linker_version=f[2],
        size_of_code=f[3],
        size_of_initialized_data=f[4],
        size_of_uninitialized_data=f[5],
        address_of_entry_point=f[6],
        base_of_code=f[7],
        image_base=f[8],
        section_alignment=f[9],
        file_alignment=f[10],
        major_os_version=f[11],
        minor_os_version=f[12],
        major_image_version=f[13],
        minor_image_version=f[14],
        major_subsystem_version=f[15],
        minor_subsystem_version=f[16],
        win32_version_value=f[17],
        size_of_image=f[18],
        size_of_headers=f[19],
        checksum=f[20],
        subsystem=f[21],
        dll_characteristics=f[22],
        size_of_stack_reserve=f[23],
        size_of_stack_commit=f[24],
        size_of_heap_reserve=f[25],
        size_of_heap_commit=f[26],
        loader_flags=f[27],
        number_of_rva_and_sizes=f[28],
        data_directories=directories,
    )


def _read_data_directories(data: bytes, offset: int, count: int) -> tuple[tuple[int, int], ...]:
    dirs: list[tuple[int, int]] = []
    pos = offset
    for _ in range(min(count, 16)):
        rva, size = struct.unpack_from("<II", data, pos)
        dirs.append((rva, size))
        pos += 8
    while len(dirs) < 16:
        dirs.append((0, 0))
    return tuple(dirs[:16])
