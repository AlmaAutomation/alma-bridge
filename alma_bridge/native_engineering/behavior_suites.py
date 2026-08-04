"""Behavior test suite definitions per implemented Win32 API."""

from __future__ import annotations

from typing import Dict, List

from alma_bridge.native_engineering.models import BehaviorTestCase, BehaviorTestSuite, TestScenarioStatus

FIXTURES_ROOT = "tests/fixtures/native_runtime/bin"


def _case(
    case_id: str,
    description: str,
    expected: str,
    *,
    fixture: str | None = None,
    behavior_id: str = "",
    status: TestScenarioStatus = TestScenarioStatus.PENDING,
) -> BehaviorTestCase:
    path = f"{FIXTURES_ROOT}/{fixture}" if fixture else None
    return BehaviorTestCase(
        case_id=case_id,
        description=description,
        expected_outcome=expected,
        fixture_path=path,
        behavior_id=behavior_id,
        status=status,
    )


def _suite(api_symbol: str, suite_id: str, cases: List[BehaviorTestCase]) -> BehaviorTestSuite:
    return BehaviorTestSuite(
        api_symbol=api_symbol,
        suite_id=suite_id,
        cases=cases,
        coverage_summary=f"{len(cases)} scenarios for {api_symbol}",
    )


def build_writefile_suite() -> BehaviorTestSuite:
    return _suite(
        "WriteFile",
        "writefile_m2_v1",
        [
            _case("writefile_console_stdout", "Write to stdout handle", "TRUE, bytes written", fixture="hello64.exe", behavior_id="write_stdout"),
            _case("writefile_console_stdout_dedicated", "Dedicated stdout fixture", "TRUE, bytes written", fixture="stdout_write.exe", behavior_id="write_stdout"),
            _case("writefile_console_stderr", "Write to stderr handle", "TRUE, bytes written", fixture="stderr_write.exe", behavior_id="write_stderr"),
            _case("writefile_regular_file", "Write to file handle", "TRUE, bytes written", fixture="file_write.exe", behavior_id="sequential_write"),
            _case("writefile_zero_length", "Zero-length write", "TRUE, 0 bytes written", behavior_id="sequential_write"),
            _case("writefile_invalid_handle", "Invalid handle rejected", "FALSE, ERROR_INVALID_HANDLE", behavior_id="sequential_write"),
            _case("writefile_append_existing", "Append to file handle", "TRUE, bytes appended at EOF", fixture="append_existing_success.exe", behavior_id="append_existing_file"),
            _case("writefile_append_repeated", "Repeated append cycles", "content preserved and extended", fixture="append_repeated.exe", behavior_id="append_existing_file"),
            _case("writefile_append_zero_length", "Zero-length append write", "TRUE, 0 bytes written", fixture="append_zero_length.exe", behavior_id="append_existing_file"),
            _case("writefile_append_invalid_handle", "Invalid handle rejected", "FALSE, ERROR_INVALID_HANDLE", fixture="append_invalid_handle.exe", behavior_id="append_existing_file"),
            _case("writefile_append_overlapped_unsupported", "Overlapped append unsupported", "FALSE, ERROR_NOT_SUPPORTED", fixture="append_overlapped_unsupported.exe", behavior_id="overlapped_io", status=TestScenarioStatus.PASS),
            _case("writefile_overlapped_unsupported", "Overlapped I/O unsupported (general)", "documented unsupported", behavior_id="overlapped_io", status=TestScenarioStatus.NOT_APPLICABLE),
        ],
    )


def build_createfilew_suite() -> BehaviorTestSuite:
    return _suite(
        "CreateFileW",
        "createfilew_m2_v1",
        [
            _case("createfilew_existing_read", "Open existing for read", "valid handle", fixture="file_read.exe", behavior_id="sequential_read"),
            _case("createfilew_create_new", "CREATE_ALWAYS create", "valid handle, file created", fixture="file_write.exe", behavior_id="create_always_write"),
            _case("createfilew_truncate", "CREATE_ALWAYS truncates", "file truncated", fixture="file_write.exe", behavior_id="create_always_write"),
            _case("createfilew_access_denied", "Path outside sandbox", "INVALID_HANDLE, ERROR_ACCESS_DENIED", behavior_id="create_always_write"),
            _case("createfilew_append_existing", "OPEN_EXISTING + FILE_APPEND_DATA", "valid handle, append at EOF", fixture="append_existing_success.exe", behavior_id="append_existing_file"),
            _case("createfilew_append_unicode", "Unicode filename append", "valid handle", fixture="append_unicode.exe", behavior_id="append_existing_file"),
            _case("createfilew_append_missing", "Missing file rejected", "INVALID_HANDLE, ERROR_FILE_NOT_FOUND", fixture="append_missing_file.exe", behavior_id="append_existing_file"),
            _case("createfilew_append_traversal", "Path traversal rejected", "INVALID_HANDLE, ERROR_ACCESS_DENIED", fixture="append_path_traversal.exe", behavior_id="append_existing_file"),
            _case("createfilew_append_unsupported", "Historical gap fixture passes", "append succeeds", fixture="file_append_unsupported.exe", behavior_id="append_existing_file", status=TestScenarioStatus.PENDING),
        ],
    )


def build_getenv_suite() -> BehaviorTestSuite:
    return _suite(
        "GetEnvironmentVariableW",
        "getenv_m2_v1",
        [
            _case("getenv_existing", "Read existing variable", "value copied", fixture="environment_read.exe", behavior_id="read_environment_variable"),
            _case("getenv_missing", "Missing variable", "0, ERROR_ENVVAR_NOT_FOUND", behavior_id="read_environment_variable"),
            _case("getenv_buffer_too_small", "Buffer too small", "required size returned", behavior_id="read_environment_variable"),
            _case("getenv_unicode", "Unicode value preserved", "UTF-16 code units", fixture="environment_read.exe", behavior_id="read_environment_variable"),
        ],
    )


def build_exitprocess_suite() -> BehaviorTestSuite:
    return _suite(
        "ExitProcess",
        "exitprocess_m2_v1",
        [
            _case("exitprocess_zero", "Exit code 0", "process exits 0", fixture="hello64.exe", behavior_id="process_exit_with_code"),
            _case("exitprocess_nonzero", "Non-zero exit code", "exit code preserved", fixture="exit_code.exe", behavior_id="process_exit_with_code"),
        ],
    )


def build_getstdhandle_suite() -> BehaviorTestSuite:
    return _suite(
        "GetStdHandle",
        "getstdhandle_m2_v1",
        [
            _case("getstdhandle_stdout", "STD_OUTPUT_HANDLE", "handle 1", fixture="hello64.exe", behavior_id="write_stdout"),
            _case("getstdhandle_stderr", "STD_ERROR_HANDLE", "handle 2", fixture="stderr_write.exe", behavior_id="write_stderr"),
            _case("getstdhandle_invalid_n", "Unknown nStdHandle", "INVALID_HANDLE_VALUE", behavior_id="write_stdout"),
        ],
    )


def build_readfile_suite() -> BehaviorTestSuite:
    return _suite(
        "ReadFile",
        "readfile_m2_v1",
        [
            _case("readfile_sequential", "Sequential read", "TRUE, bytes read", fixture="file_read.exe", behavior_id="sequential_read"),
            _case("readfile_invalid_handle", "Invalid handle", "FALSE", behavior_id="sequential_read"),
        ],
    )


def build_getcommandlinew_suite() -> BehaviorTestSuite:
    return _suite(
        "GetCommandLineW",
        "getcommandlinew_m2_v1",
        [
            _case("getcommandline_unicode", "Unicode command line", "UTF-16 pointer", fixture="unicode_argv.exe", behavior_id="read_command_line"),
        ],
    )


def build_closehandle_suite() -> BehaviorTestSuite:
    return _suite(
        "CloseHandle",
        "closehandle_m2_v1",
        [
            _case("closehandle_file", "Close file handle", "TRUE", fixture="file_write.exe", behavior_id="close_handle"),
        ],
    )


def build_minimal_suite(api_symbol: str, behavior_id: str) -> BehaviorTestSuite:
    return _suite(
        api_symbol,
        f"{api_symbol.lower()}_m2_v1",
        [_case(f"{api_symbol.lower()}_basic", f"Basic {api_symbol} behavior", "documented in spec", behavior_id=behavior_id)],
    )


_SUITE_BUILDERS = {
    "WriteFile": build_writefile_suite,
    "CreateFileW": build_createfilew_suite,
    "GetEnvironmentVariableW": build_getenv_suite,
    "ExitProcess": build_exitprocess_suite,
    "GetStdHandle": build_getstdhandle_suite,
    "ReadFile": build_readfile_suite,
    "GetCommandLineW": build_getcommandlinew_suite,
    "CloseHandle": build_closehandle_suite,
}


def get_behavior_suite(api_symbol: str) -> BehaviorTestSuite:
    builder = _SUITE_BUILDERS.get(api_symbol)
    if builder:
        return builder()
    from alma_bridge.native_engineering.specifications import API_CAPABILITY_MAP

    cap, behaviors = API_CAPABILITY_MAP.get(api_symbol, ("unknown", ["unknown"]))
    _ = cap
    bid = behaviors[0] if behaviors else "unknown"
    return build_minimal_suite(api_symbol, bid)


def get_all_behavior_suites() -> Dict[str, BehaviorTestSuite]:
    from alma_bridge.native_engineering.specifications import list_api_symbols

    return {sym: get_behavior_suite(sym) for sym in list_api_symbols()}
