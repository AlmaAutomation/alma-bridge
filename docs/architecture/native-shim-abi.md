# Native Kernel32 Shim ABI (Milestone 2)

## Library

Built as `libalma_native_shim.so` from `pe_loader.c` + `kernel32_shim.c`.

## Init

```c
void alma_native_init_ex(
    const char *workspace,
    const void *command_line_utf16le,
    const char *env_block  /* KEY=VALUE lines, null-terminated */
);
```

## Run

```c
int32_t alma_native_load_and_run(
    const uint8_t *pe_data,
    size_t pe_size,
    uint64_t load_base_override  /* 0 = use ImageBase for delta math only */
);
```

## Evidence getters

- `alma_native_get_stdout` / `alma_native_get_stderr`
- `alma_native_get_stdout_len` / `alma_native_get_stderr_len`
- `alma_native_get_entrypoint_invoked`
- `alma_native_get_simulation_used`
- `alma_native_get_execution_mode`

## Supported kernel32 exports

`GetStdHandle`, `WriteFile`, `ReadFile`, `CreateFileW`, `CloseHandle`,
`GetCommandLineW`, `GetEnvironmentVariableW`, `GetLastError`, `SetLastError`,
`GetModuleFileNameW`, `GetCurrentProcessId`, `Sleep`, `ExitProcess`.

All shims use `__attribute__((ms_abi))` on x86_64. Wide-string parameters use
UTF-16LE regardless of host `wchar_t` width.

## Filesystem

`CreateFileW` / `ReadFile` / `WriteFile` resolve paths under the workspace root
only (mirrors Python `filesystem/paths.py` policy).
