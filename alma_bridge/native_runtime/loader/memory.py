"""Virtual memory mapping for PE images."""

from __future__ import annotations

import mmap
from typing import Optional


def allocate_image(size: int) -> mmap.mmap:
    """Allocate zero-filled RW memory for PE image."""
    return mmap.mmap(-1, size, prot=mmap.PROT_READ | mmap.PROT_WRITE)


def protect_executable(region: mmap.mmap, offset: int, size: int) -> None:
    """Mark region executable (best-effort on Linux via mprotect)."""
    import ctypes
    import ctypes.util

    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    page_size = mmap.PAGESIZE
    start = (offset // page_size) * page_size
    end = ((offset + size + page_size - 1) // page_size) * page_size
    length = end - start
    addr = ctypes.c_void_p(ctypes.addressof(ctypes.c_char.from_buffer(region, start)))
    prot = mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC
    if libc.mprotect(addr, length, prot) != 0:
        raise OSError("mprotect failed")
