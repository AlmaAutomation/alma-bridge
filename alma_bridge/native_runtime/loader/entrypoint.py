"""PE entrypoint invocation."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Optional

from alma_bridge.native_runtime.errors import ExecutionError, REASON_EXEC_FAILED, REASON_SHIM_MISSING
from alma_bridge.native_runtime.loader.image import LoadedImage
from alma_bridge.native_runtime.tracing import trace


def shim_library_path() -> Path:
    root = Path(__file__).resolve().parents[1]
    candidates = [
        root / "shim" / "libalma_native_shim.so",
        Path(os.environ.get("ALMA_NATIVE_SHIM_PATH", "")),
    ]
    for path in candidates:
        if path and path.is_file():
            return path
    return root / "shim" / "libalma_native_shim.so"


def shim_available() -> bool:
    return shim_library_path().is_file()


def invoke_entry(loaded: LoadedImage, *, workspace: Path) -> int:
    """Invoke PE entry via C trampoline and kernel32 shim library."""
    shim_path = shim_library_path()
    if not shim_path.is_file():
        raise ExecutionError(
            f"shim library not found: {shim_path}",
            reason_codes=[REASON_SHIM_MISSING],
        )
    lib = ctypes.CDLL(str(shim_path))
    lib.alma_native_init.argtypes = [ctypes.c_char_p]
    lib.alma_native_init.restype = None
    lib.alma_native_run_pe.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint64,
        ctypes.c_uint32,
    ]
    lib.alma_native_run_pe.restype = ctypes.c_int32
    lib.alma_native_get_stdout.argtypes = []
    lib.alma_native_get_stdout.restype = ctypes.c_char_p
    lib.alma_native_get_stderr.argtypes = []
    lib.alma_native_get_stderr.restype = ctypes.c_char_p

    lib.alma_native_init(str(workspace).encode("utf-8"))
    buf = (ctypes.c_char * len(loaded.image)).from_buffer_copy(bytes(loaded.image))
    exit_code = lib.alma_native_run_pe(
        ctypes.cast(buf, ctypes.c_void_p),
        ctypes.c_uint64(loaded.base_address),
        ctypes.c_uint32(loaded.entry_rva),
    )
    trace(f"entry returned exit_code={exit_code}")
    return int(exit_code)


def capture_shim_output() -> tuple[str, str]:
    shim_path = shim_library_path()
    if not shim_path.is_file():
        return "", ""
    lib = ctypes.CDLL(str(shim_path))
    lib.alma_native_get_stdout.restype = ctypes.c_char_p
    lib.alma_native_get_stderr.restype = ctypes.c_char_p
    out = lib.alma_native_get_stdout() or b""
    err = lib.alma_native_get_stderr() or b""
    return out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace")
