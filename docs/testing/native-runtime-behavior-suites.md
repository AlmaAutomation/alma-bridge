# Native Runtime Behavior Test Suites

Behavior test suite definitions for NativeAlmaRuntime M2 kernel32 shims.
Suites are declared in `alma_bridge/native_engineering/behavior_suites.py`
and mapped to fixtures under `tests/fixtures/native_runtime/`.

## Fixture catalog

| Fixture | Behaviors exercised | APIs |
|---------|---------------------|------|
| `hello64.exe` | write_stdout, process_exit_with_code | GetStdHandle, WriteFile, ExitProcess |
| `stdout_write.exe` | write_stdout | GetStdHandle, WriteFile, ExitProcess |
| `stderr_write.exe` | write_stderr | GetStdHandle, WriteFile, ExitProcess |
| `exit_code.exe` | process_exit_with_code (non-zero) | ExitProcess |
| `file_write.exe` | create_always_write, sequential_write | CreateFileW, WriteFile, CloseHandle |
| `file_read.exe` | sequential_read | CreateFileW, ReadFile, CloseHandle |
| `file_append_unsupported.exe` | append_existing_file (unsupported) | CreateFileW, WriteFile |
| `environment_read.exe` | read_environment_variable | GetEnvironmentVariableW, ExitProcess |
| `unicode_argv.exe` | read_command_line | GetCommandLineW, ExitProcess |

Build fixtures: `tests/fixtures/native_runtime/build_fixtures.sh`

## WriteFile scenarios

| Scenario ID | Expected | Fixture / case |
|-------------|----------|----------------|
| `writefile_console_stdout` | success, bytes written | hello64.exe, stdout_write.exe |
| `writefile_console_stderr` | success, bytes written | stderr_write.exe |
| `writefile_regular_file` | success via fd handle | file_write.exe |
| `writefile_zero_length` | success, 0 bytes | defined case |
| `writefile_invalid_handle` | FALSE, ERROR_INVALID_HANDLE | defined case |
| `writefile_overlapped_unsupported` | unsupported behavior documented | spec only |

## CreateFileW scenarios

| Scenario ID | Expected | Fixture / case |
|-------------|----------|----------------|
| `createfilew_existing_read` | open existing for read | file_read.exe |
| `createfilew_create_new` | CREATE_ALWAYS truncate/create | file_write.exe |
| `createfilew_truncate` | CREATE_ALWAYS truncates | file_write.exe |
| `createfilew_access_denied` | ERROR_ACCESS_DENIED outside sandbox | defined case |
| `createfilew_append_unsupported` | failure / unsupported | file_append_unsupported.exe |

## GetEnvironmentVariableW scenarios

| Scenario ID | Expected | Fixture |
|-------------|----------|---------|
| `getenv_existing` | value copied, length returned | environment_read.exe |
| `getenv_missing` | 0, ERROR_ENVVAR_NOT_FOUND | defined case |
| `getenv_buffer_too_small` | truncated with required size | defined case |
| `getenv_unicode` | UTF-16 code units preserved | environment_read.exe |

## ExitProcess scenarios

| Scenario ID | Expected | Fixture |
|-------------|----------|---------|
| `exitprocess_zero` | exit code 0 | hello64.exe |
| `exitprocess_nonzero` | exit code preserved | exit_code.exe |

## GetStdHandle scenarios

| Scenario ID | Expected |
|-------------|----------|
| `getstdhandle_stdout` | handle 1 |
| `getstdhandle_stderr` | handle 2 |
| `getstdhandle_invalid_n` | INVALID_HANDLE_VALUE |

## Unsupported behavior documentation

`file_append_unsupported.exe` validates that `append_existing_file` remains
**unsupported** for native_alma. The engineering spec documents this; the
fixture is in the manifest but excluded from the execution allowlist.

## Running suites

Behavior suite definitions are verified by pytest in `tests/native_engineering/`.
Runtime execution benchmarks run only when the native shim is built and flags
allow experimental execution — never from HTTP GET endpoints.
