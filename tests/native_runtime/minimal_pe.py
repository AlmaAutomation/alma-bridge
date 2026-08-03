"""Shared synthetic PE bytes for native_runtime tests."""

from __future__ import annotations

import struct

from alma_bridge.native_runtime.pe.headers import IMAGE_SUBSYSTEM_WINDOWS_CUI


def minimal_pe_bytes(*, subsystem: int = IMAGE_SUBSYSTEM_WINDOWS_CUI, machine: int = 0x8664) -> bytes:
    dos = bytearray(128)
    struct.pack_into("<H", dos, 0, 0x5A4D)
    struct.pack_into("<I", dos, 60, 128)
    opt_size = 224 if machine == 0x14C else 240
    magic = 0x10B if machine == 0x14C else 0x20B
    coff = struct.pack("<HHIIIHH", machine, 1, 0, 0, 0, opt_size, 0x22)
    opt = bytearray(opt_size)
    struct.pack_into("<H", opt, 0, magic)
    struct.pack_into("<I", opt, 16, 0x1000)
    struct.pack_into("<I", opt, 56, 0x3000)
    struct.pack_into("<I", opt, 60, 0x200)
    struct.pack_into("<H", opt, 68, subsystem)
    struct.pack_into("<I", opt, 92 if machine == 0x14C else 108, 16)
    if machine == 0x8664:
        struct.pack_into("<Q", opt, 24, 0x140000000)
    else:
        struct.pack_into("<I", opt, 28, 0x400000)
    sec = struct.pack(
        "<8sIIIIIIHHI",
        b".text\x00\x00\x00",
        0x100,
        0x1000,
        0x100,
        0x200,
        0,
        0,
        0,
        0,
        0x60000020,
    )
    return bytes(dos + b"PE\x00\x00" + coff + opt + sec + b"\x00" * 0x200)
