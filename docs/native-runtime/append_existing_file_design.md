# append_existing_file — Bounded Design Specification

**Work item:** `wi_native_alma_filesystem_basic_io_append_existing_file_v1`  
**Provider:** `native_alma`  
**Capability:** `filesystem.basic_io`  
**Behavior:** `append_existing_file`  
**Implementation version:** `0.2.1-m2`

## Scope

PE64 console binaries may append bytes to an **existing regular file** within the
runtime workspace using:

- `CreateFileW` with `OPEN_EXISTING` and `FILE_APPEND_DATA`
- synchronous `WriteFile` (no `OVERLAPPED`)
- `CloseHandle` for handle cleanup

## CreateFileW Semantics

| Parameter | Supported value | Notes |
|-----------|-----------------|-------|
| `lpFileName` | Workspace-relative UTF-16 path | Resolved under `g_workspace`; `\` → `/` |
| `dwDesiredAccess` | `FILE_APPEND_DATA` (0x0004) | Required for append path |
| `dwShareMode` | Ignored | Shared handles not modeled |
| `dwCreationDisposition` | `OPEN_EXISTING` (3) only | Must not create or truncate |
| `dwFlagsAndAttributes` | Ignored for append | `FILE_ATTRIBUTE_NORMAL` accepted |
| `hTemplateFile` | Ignored | |

**Success:** Returns opaque handle slot `>= 10` backed by host `open(O_RDWR|O_APPEND)`.

**Failure modes:**

| Condition | Return | `GetLastError` |
|-----------|--------|----------------|
| Path contains `..` | `INVALID_HANDLE_VALUE` | `ERROR_ACCESS_DENIED` (3) |
| File does not exist | `INVALID_HANDLE_VALUE` | `ERROR_FILE_NOT_FOUND` (2) |
| `OPEN_EXISTING` + missing file | `INVALID_HANDLE_VALUE` | `ERROR_FILE_NOT_FOUND` (2) |
| Disposition other than `OPEN_EXISTING` with append access | `INVALID_HANDLE_VALUE` | `ERROR_INVALID_PARAMETER` (87) |
| Handle table full | `INVALID_HANDLE_VALUE` | (unspecified) |

## WriteFile Semantics

| Condition | Result |
|-----------|--------|
| Valid append handle, `lpOverlapped == NULL` | `TRUE`; bytes written at EOF via host `write()` with `O_APPEND` |
| Zero-length write | `TRUE`; `*lpNumberOfBytesWritten = 0` |
| `lpOverlapped != NULL` | `FALSE`; `ERROR_NOT_SUPPORTED` (50) |
| Invalid / closed handle | `FALSE`; `ERROR_INVALID_HANDLE` (6) |

Partial writes follow host `write()` behavior. Content already in the file is preserved.

## Handle Model

```text
file_handle_t { fd, is_file, append_mode }
  slots 10..(10+MAX_FILES-1)  → workspace file descriptors
  handles 1, 2               → stdout/stderr (unchanged)
```

Append handles set `append_mode = 1`. Regular write handles (`CREATE_ALWAYS`) keep
`append_mode = 0`.

## Filesystem Policy

- All paths resolved relative to workspace root (`g_workspace`).
- Absolute paths outside workspace rejected (`ERROR_ACCESS_DENIED`).
- Path traversal (`..`) rejected before `open()`.
- Symlinks: host `open()` follows symlinks; confinement enforced by path resolution only.
- No unbounded growth guard beyond host filesystem limits (documented limitation).

## Explicitly Unsupported (Preserved)

| Feature | Rationale |
|---------|-----------|
| Overlapped / async I/O | Out of M2 scope; `lpOverlapped != NULL` → `ERROR_NOT_SUPPORTED` |
| Shared handles / share modes | Not modeled |
| Arbitrary host absolute paths | Workspace confinement |
| `CREATE_ALWAYS` / truncate via append access | Append requires existing file |
| Wine delegation for append | Native shim only |
| Auto-promotion of capability maturity | Governance review required |

## Fixture Coverage

| Fixture | Validates |
|---------|-----------|
| `append_existing_success.exe` | Basic append preserves + extends content |
| `append_repeated.exe` | Multiple open/append/close cycles |
| `append_unicode.exe` | UTF-16 filename within workspace |
| `append_zero_length.exe` | Zero-byte WriteFile succeeds |
| `append_invalid_handle.exe` | Invalid handle rejected |
| `append_missing_file.exe` | Missing target fails closed |
| `append_path_traversal.exe` | `..` rejected |
| `append_overlapped_unsupported.exe` | Overlapped WriteFile rejected |
| `file_append_unsupported.exe` | Historical gap fixture → passes after implementation |

## Security Boundaries

- Workspace confinement enforced in `resolve_workspace_path`.
- Handle slots bounded by `MAX_FILES` (32).
- File descriptors opened with `O_CLOEXEC`.
- No fixture-name branching in runtime code.
