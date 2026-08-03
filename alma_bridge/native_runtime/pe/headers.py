"""PE header constants and structures."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Tuple

IMAGE_DOS_SIGNATURE = 0x5A4D
IMAGE_NT_SIGNATURE = 0x00004550
IMAGE_NT_OPTIONAL_HDR32_MAGIC = 0x10B
IMAGE_NT_OPTIONAL_HDR64_MAGIC = 0x20B

IMAGE_FILE_MACHINE_I386 = 0x014C
IMAGE_FILE_MACHINE_AMD64 = 0x8664

IMAGE_SUBSYSTEM_UNKNOWN = 0
IMAGE_SUBSYSTEM_NATIVE = 1
IMAGE_SUBSYSTEM_WINDOWS_GUI = 2
IMAGE_SUBSYSTEM_WINDOWS_CUI = 3

IMAGE_DIRECTORY_ENTRY_IMPORT = 1
IMAGE_DIRECTORY_ENTRY_BASERELOC = 5
IMAGE_DIRECTORY_ENTRY_TLS = 9
IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT = 13

IMAGE_REL_BASED_ABSOLUTE = 0
IMAGE_REL_BASED_HIGHLOW = 3
IMAGE_REL_BASED_DIR64 = 10

DLL_CHARACTERISTICS_DYNAMIC_BASE = 0x0040


@dataclass(frozen=True)
class DOSHeader:
    e_magic: int
    e_lfanew: int


@dataclass(frozen=True)
class COFFHeader:
    machine: int
    number_of_sections: int
    time_date_stamp: int
    pointer_to_symbol_table: int
    number_of_symbols: int
    size_of_optional_header: int
    characteristics: int


@dataclass(frozen=True)
class OptionalHeader:
    magic: int
    major_linker_version: int
    minor_linker_version: int
    size_of_code: int
    size_of_initialized_data: int
    size_of_uninitialized_data: int
    address_of_entry_point: int
    base_of_code: int
    image_base: int
    section_alignment: int
    file_alignment: int
    major_os_version: int
    minor_os_version: int
    major_image_version: int
    minor_image_version: int
    major_subsystem_version: int
    minor_subsystem_version: int
    win32_version_value: int
    size_of_image: int
    size_of_headers: int
    checksum: int
    subsystem: int
    dll_characteristics: int
    size_of_stack_reserve: int
    size_of_stack_commit: int
    size_of_heap_reserve: int
    size_of_heap_commit: int
    loader_flags: int
    number_of_rva_and_sizes: int
    data_directories: Tuple[Tuple[int, int], ...]
    # PE32-only
    base_of_data: int = 0


def machine_name(machine: int) -> str:
    if machine == IMAGE_FILE_MACHINE_AMD64:
        return "amd64"
    if machine == IMAGE_FILE_MACHINE_I386:
        return "i386"
    return f"unknown_{machine:#x}"


def subsystem_name(subsystem: int) -> str:
    names = {
        IMAGE_SUBSYSTEM_WINDOWS_CUI: "console",
        IMAGE_SUBSYSTEM_WINDOWS_GUI: "gui",
        IMAGE_SUBSYSTEM_NATIVE: "native",
        IMAGE_SUBSYSTEM_UNKNOWN: "unknown",
    }
    return names.get(subsystem, f"unknown_{subsystem}")




def read_dos_header(data: bytes) -> DOSHeader:
    if len(data) < 64:
        raise ValueError("file too small for DOS header")
    e_magic = struct.unpack_from("<H", data, 0)[0]
    e_lfanew = struct.unpack_from("<I", data, 60)[0]
    if e_magic != IMAGE_DOS_SIGNATURE:
        raise ValueError(f"invalid DOS signature: {e_magic:#x}")
    return DOSHeader(e_magic=e_magic, e_lfanew=e_lfanew)


def read_coff_header(data: bytes, offset: int) -> COFFHeader:
    fmt = "<HHIIIHH"
    fields = struct.unpack_from(fmt, data, offset)
    return COFFHeader(
        machine=fields[0],
        number_of_sections=fields[1],
        time_date_stamp=fields[2],
        pointer_to_symbol_table=fields[3],
        number_of_symbols=fields[4],
        size_of_optional_header=fields[5],
        characteristics=fields[6],
    )
