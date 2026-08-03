"""PE entrypoint invocation via C loader."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Dict, List, Optional

from alma_bridge.native_runtime.errors import ExecutionError, REASON_EXEC_FAILED, REASON_SHIM_MISSING
from alma_bridge.native_runtime.loader.image import LoadedImage
from alma_bridge.native_runtime.process.command_line import build_command_line_utf16le
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


def _load_shim():
    shim_path = shim_library_path()
    if not shim_path.is_file():
        raise ExecutionError(
            f"shim library not found: {shim_path}",
            reason_codes=[REASON_SHIM_MISSING],
        )
    return ctypes.CDLL(str(shim_path))


def invoke_native_load_and_run(
    pe_bytes: bytes,
    *,
    workspace: Path,
    argv: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None,
    load_base_override: int = 0,
) -> tuple[int, bool, bool, str]:
    """Run PE via C loader; returns (exit_code, entrypoint_invoked, simulation_used, mode)."""
    lib = _load_shim()
    lib.alma_native_init_ex.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_char_p]
    lib.alma_native_init_ex.restype = None
    lib.alma_native_load_and_run.argtypes = [
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_uint64,
    ]
    lib.alma_native_load_and_run.restype = ctypes.c_int32
    lib.alma_native_get_entrypoint_invoked.argtypes = []
    lib.alma_native_get_entrypoint_invoked.restype = ctypes.c_int
    lib.alma_native_get_simulation_used.argtypes = []
    lib.alma_native_get_simulation_used.restype = ctypes.c_int
    lib.alma_native_get_execution_mode.argtypes = []
    lib.alma_native_get_execution_mode.restype = ctypes.c_char_p

    cmdline = build_command_line_utf16le(argv or ["fixture.exe"])
    env_block = ""
    if env:
        env_block = "\n".join(f"{k}={v}" for k, v in env.items()) + "\n"

    cmd_buf = (ctypes.c_char * len(cmdline)).from_buffer_copy(cmdline)
    env_ptr = None
    if env_block:
        env_bytes = env_block.encode("utf-8") + b"\0"
        env_buf = (ctypes.c_char * len(env_bytes)).from_buffer_copy(env_bytes)
        env_ptr = ctypes.cast(env_buf, ctypes.c_char_p)
    lib.alma_native_init_ex(
        str(workspace).encode("utf-8"),
        ctypes.cast(cmd_buf, ctypes.c_void_p),
        env_ptr,
    )
    buf = (ctypes.c_char * len(pe_bytes)).from_buffer_copy(pe_bytes)
    exit_code = lib.alma_native_load_and_run(
        ctypes.cast(buf, ctypes.c_void_p),
        ctypes.c_size_t(len(pe_bytes)),
        ctypes.c_uint64(load_base_override),
    )
    invoked = bool(lib.alma_native_get_entrypoint_invoked())
    simulation = bool(lib.alma_native_get_simulation_used())
    mode_raw = lib.alma_native_get_execution_mode()
    mode = mode_raw.decode("utf-8") if mode_raw else "mapped_pe_entrypoint"
    trace(f"native load_and_run exit_code={exit_code} invoked={invoked}")
    return int(exit_code), invoked, simulation, mode


def invoke_entry(
    loaded: LoadedImage,
    *,
    workspace: Path,
    argv: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None,
    load_base_override: Optional[int] = None,
) -> int:
    """Invoke PE entry via C trampoline and kernel32 shim library."""
    override = 0
    if load_base_override is not None:
        override = load_base_override
    elif loaded.base_address != loaded.parsed.optional.image_base:
        override = loaded.base_address
    exit_code, _, _, _ = invoke_native_load_and_run(
        bytes(loaded.parsed.data),
        workspace=workspace,
        argv=argv,
        env=env,
        load_base_override=override,
    )
    return exit_code


def capture_shim_output() -> tuple[str, str]:
    shim_path = shim_library_path()
    if not shim_path.is_file():
        return "", ""
    lib = ctypes.CDLL(str(shim_path))
    lib.alma_native_get_stdout.restype = ctypes.c_char_p
    lib.alma_native_get_stderr.restype = ctypes.c_char_p
    lib.alma_native_get_stdout_len.restype = ctypes.c_size_t
    lib.alma_native_get_stderr_len.restype = ctypes.c_size_t
    out_len = int(lib.alma_native_get_stdout_len())
    err_len = int(lib.alma_native_get_stderr_len())
    out_ptr = lib.alma_native_get_stdout()
    err_ptr = lib.alma_native_get_stderr()
    out = ctypes.string_at(out_ptr, out_len) if out_ptr and out_len else b""
    err = ctypes.string_at(err_ptr, err_len) if err_ptr and err_len else b""
    return out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace")
