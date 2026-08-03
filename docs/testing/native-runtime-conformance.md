# Native Runtime Conformance Testing

## Fixture catalog

Built from `tests/fixtures/native_runtime/src/` via `build_fixtures.sh` (mingw cross
compilers when available):

| Fixture | Exercises |
|---------|-----------|
| `hello64.exe` | Entry, stdout write, exit 0 |
| `hello32.exe` | 32-bit path (skip if no i686 worker) |
| `stdout_write.exe` | `WriteFile` to stdout handle |
| `stderr_write.exe` | `WriteFile` to stderr handle |
| `exit_code.exe` | Non-zero `ExitProcess` |
| `unicode_argv.exe` | `GetCommandLineW` |
| `environment_read.exe` | `GetEnvironmentVariableW` |
| `file_read.exe` | `CreateFileW` + `ReadFile` |
| `file_write.exe` | `CreateFileW` + `WriteFile` |

All fixtures link **kernel32.dll only** (`-nostdlib` custom entry).

## Test numbering

| Range | Area |
|-------|------|
| 1–10 | PE parser (headers, sections, imports, relocations) |
| 11–17 | Eligibility |
| 18–33 | Loader and runtime |
| 34–38 | Authority / boundary (no VerificationGateway import) |
| 39–45 | Conformance (Wine vs native baseline) |

Execution tests skip when fixtures or shim `.so` are not built (`pytest.mark.skipif`).

## Running

```bash
# Build fixtures (optional)
tests/fixtures/native_runtime/build_fixtures.sh

# Run native runtime tests
pytest tests/native_runtime/ tests/runtime/ -v
```

## Conformance classification

Uses existing `runtime/conformance/comparison.py` signals: `exit_code`, `stdout`,
`stderr`. Native candidate must not raise `RuntimeNotSupportedError` when flags
enabled and fixture eligible.
