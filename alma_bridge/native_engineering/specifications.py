"""Deterministic API specifications for NativeAlmaRuntime M2 kernel32 shims."""

from __future__ import annotations

from typing import Dict, List

from alma_bridge.native_engineering.digest import digest_of
from alma_bridge.native_engineering.models import ApiSpecification, ErrorMode, ParameterSpec

FIXTURES_ROOT = "tests/fixtures/native_runtime/bin"

_SPECS: Dict[str, ApiSpecification] = {}


def _build_specs() -> Dict[str, ApiSpecification]:
    specs: Dict[str, ApiSpecification] = {}

    def add(spec: ApiSpecification) -> None:
        body = spec.model_dump(mode="json", exclude={"spec_digest"})
        spec.spec_digest = digest_of(body)
        specs[spec.api_symbol] = spec

    add(
        ApiSpecification(
            api_symbol="WriteFile",
            parameters=[
                ParameterSpec(name="hFile", type_name="HANDLE"),
                ParameterSpec(name="lpBuffer", type_name="LPCVOID"),
                ParameterSpec(name="nNumberOfBytesToWrite", type_name="DWORD"),
                ParameterSpec(name="lpNumberOfBytesWritten", type_name="LPDWORD", nullable=True),
                ParameterSpec(name="lpOverlapped", type_name="LPOVERLAPPED", nullable=True),
            ],
            return_type="BOOL",
            success_semantics="Returns TRUE; sets bytes written when out pointer provided.",
            error_modes=[
                ErrorMode(condition="invalid handle", error_name="ERROR_INVALID_HANDLE", return_value="FALSE"),
                ErrorMode(condition="overlapped I/O requested", error_name="ERROR_NOT_SUPPORTED", return_value="FALSE"),
            ],
            supported_behaviors=["write_stdout", "write_stderr", "sequential_write"],
            unsupported_behaviors=["overlapped_io"],
            limitations=["Handles 1/2 route to console buffers; fd handles >= 10 use host write()"],
        )
    )

    add(
        ApiSpecification(
            api_symbol="CreateFileW",
            parameters=[
                ParameterSpec(name="lpFileName", type_name="LPCWSTR"),
                ParameterSpec(name="dwDesiredAccess", type_name="DWORD"),
                ParameterSpec(name="dwShareMode", type_name="DWORD"),
                ParameterSpec(name="lpSecurityAttributes", type_name="LPSECURITY_ATTRIBUTES", nullable=True),
                ParameterSpec(name="dwCreationDisposition", type_name="DWORD"),
                ParameterSpec(name="dwFlagsAndAttributes", type_name="DWORD"),
                ParameterSpec(name="hTemplateFile", type_name="HANDLE", nullable=True),
            ],
            return_type="HANDLE",
            success_semantics="Returns file handle slot >= 10 on success.",
            error_modes=[
                ErrorMode(condition="path outside workspace sandbox", error_name="ERROR_ACCESS_DENIED", return_value="INVALID_HANDLE_VALUE"),
                ErrorMode(condition="FILE_APPEND_DATA access", error_name="ERROR_NOT_SUPPORTED", return_value="INVALID_HANDLE_VALUE"),
            ],
            supported_behaviors=["create_always_write", "sequential_read", "close_handle"],
            unsupported_behaviors=["append_existing_file", "open_existing_readwrite", "overlapped_io"],
            limitations=[
                "CREATE_ALWAYS with GENERIC_WRITE supported",
                "OPEN_EXISTING without CREATE_ALWAYS not fully supported",
                "FILE_APPEND_DATA unsupported — see file_append_unsupported.exe",
            ],
        )
    )

    add(
        ApiSpecification(
            api_symbol="ReadFile",
            parameters=[
                ParameterSpec(name="hFile", type_name="HANDLE"),
                ParameterSpec(name="lpBuffer", type_name="LPVOID"),
                ParameterSpec(name="nNumberOfBytesToRead", type_name="DWORD"),
                ParameterSpec(name="lpNumberOfBytesRead", type_name="LPDWORD", nullable=True),
                ParameterSpec(name="lpOverlapped", type_name="LPOVERLAPPED", nullable=True),
            ],
            return_type="BOOL",
            success_semantics="Returns TRUE for fd handles >= 10.",
            error_modes=[
                ErrorMode(condition="invalid handle", error_name="ERROR_INVALID_HANDLE", return_value="FALSE"),
            ],
            supported_behaviors=["sequential_read"],
            unsupported_behaviors=["overlapped_io"],
        )
    )

    add(
        ApiSpecification(
            api_symbol="GetStdHandle",
            parameters=[ParameterSpec(name="nStdHandle", type_name="DWORD")],
            return_type="HANDLE",
            success_semantics="Returns 1 for STD_OUTPUT_HANDLE, 2 for STD_ERROR_HANDLE.",
            error_modes=[
                ErrorMode(condition="unknown nStdHandle", return_value="INVALID_HANDLE_VALUE"),
            ],
            supported_behaviors=["write_stdout", "write_stderr"],
        )
    )

    add(
        ApiSpecification(
            api_symbol="ExitProcess",
            parameters=[ParameterSpec(name="uExitCode", type_name="UINT")],
            return_type="VOID",
            success_semantics="Terminates process with given exit code via siglongjmp unwind.",
            supported_behaviors=["process_exit_with_code"],
        )
    )

    add(
        ApiSpecification(
            api_symbol="GetEnvironmentVariableW",
            parameters=[
                ParameterSpec(name="lpName", type_name="LPCWSTR"),
                ParameterSpec(name="lpBuffer", type_name="LPWSTR", nullable=True),
                ParameterSpec(name="nSize", type_name="DWORD"),
            ],
            return_type="DWORD",
            success_semantics="Returns character count excluding null; copies UTF-16 value.",
            error_modes=[
                ErrorMode(condition="variable not found", error_name="ERROR_ENVVAR_NOT_FOUND", return_value="0"),
                ErrorMode(condition="buffer too small", error_name="ERROR_INSUFFICIENT_BUFFER", return_value="required_size"),
            ],
            supported_behaviors=["read_environment_variable"],
            unsupported_behaviors=["set_environment_variable"],
            limitations=["Environment block from worker subprocess only; MAX_ENV=64"],
        )
    )

    add(
        ApiSpecification(
            api_symbol="GetCommandLineW",
            parameters=[],
            return_type="LPWSTR",
            success_semantics="Returns pointer to UTF-16 command line built from worker args.",
            supported_behaviors=["read_command_line"],
        )
    )

    add(
        ApiSpecification(
            api_symbol="CloseHandle",
            parameters=[ParameterSpec(name="hObject", type_name="HANDLE")],
            return_type="BOOL",
            success_semantics="Closes file slot for fd handles.",
            supported_behaviors=["close_handle"],
        )
    )

    add(
        ApiSpecification(
            api_symbol="GetLastError",
            parameters=[],
            return_type="DWORD",
            success_semantics="Returns thread-local g_last_error from shim.",
            supported_behaviors=["error_handling"],
        )
    )

    add(
        ApiSpecification(
            api_symbol="SetLastError",
            parameters=[ParameterSpec(name="dwErrCode", type_name="DWORD")],
            return_type="VOID",
            success_semantics="Sets g_last_error.",
            supported_behaviors=["error_handling"],
        )
    )

    add(
        ApiSpecification(
            api_symbol="GetModuleFileNameW",
            parameters=[
                ParameterSpec(name="hModule", type_name="HMODULE", nullable=True),
                ParameterSpec(name="lpFilename", type_name="LPWSTR"),
                ParameterSpec(name="nSize", type_name="DWORD"),
            ],
            return_type="DWORD",
            success_semantics="Returns length; path is <workspace>/fixture.exe.",
            supported_behaviors=["module_identity"],
        )
    )

    add(
        ApiSpecification(
            api_symbol="GetCurrentProcessId",
            parameters=[],
            return_type="DWORD",
            success_semantics="Returns host getpid().",
            supported_behaviors=["process_identity"],
        )
    )

    add(
        ApiSpecification(
            api_symbol="Sleep",
            parameters=[ParameterSpec(name="dwMilliseconds", type_name="DWORD")],
            return_type="VOID",
            success_semantics="Blocks via usleep(ms*1000).",
            supported_behaviors=["process_timing"],
        )
    )

    return specs


def list_api_symbols() -> List[str]:
    return sorted(get_all_specifications().keys())


def get_specification(api_symbol: str) -> ApiSpecification:
    specs = get_all_specifications()
    key = api_symbol
    if key not in specs:
        for sym in specs:
            if sym.lower() == api_symbol.lower():
                key = sym
                break
    if key not in specs:
        from alma_bridge.native_engineering.errors import SpecificationNotFoundError

        raise SpecificationNotFoundError(f"No specification for API '{api_symbol}'")
    return specs[key]


def get_all_specifications() -> Dict[str, ApiSpecification]:
    global _SPECS
    if not _SPECS:
        _SPECS = _build_specs()
    return _SPECS


# API → capability/behavior mapping for profiles
API_CAPABILITY_MAP: Dict[str, tuple[str, List[str]]] = {
    "WriteFile": ("console.stdout", ["write_stdout", "write_stderr", "sequential_write"]),
    "CreateFileW": ("filesystem.basic_io", ["create_always_write", "sequential_read", "close_handle"]),
    "ReadFile": ("filesystem.basic_io", ["sequential_read"]),
    "GetStdHandle": ("console.stdout", ["write_stdout", "write_stderr"]),
    "ExitProcess": ("process.exit", ["process_exit_with_code"]),
    "GetEnvironmentVariableW": ("process.environment", ["read_environment_variable"]),
    "GetCommandLineW": ("process.arguments", ["read_command_line"]),
    "CloseHandle": ("filesystem.basic_io", ["close_handle"]),
    "GetLastError": ("error.handling", ["error_handling"]),
    "SetLastError": ("error.handling", ["error_handling"]),
    "GetModuleFileNameW": ("process.identity", ["module_identity"]),
    "GetCurrentProcessId": ("process.identity", ["process_identity"]),
    "Sleep": ("process.timing", ["process_timing"]),
}
