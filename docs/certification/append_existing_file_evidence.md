# append_existing_file — Certification Evidence Record

**Work item:** `wi_native_alma_filesystem_basic_io_append_existing_file_v1`  
**Provider:** `native_alma`  
**Implementation version:** `0.2.1-m2`  
**Review date:** 2026-08-04

## Summary

Bounded workspace-confined append via `CreateFileW(OPEN_EXISTING, FILE_APPEND_DATA)` and
synchronous `WriteFile` was implemented, tested, verified, and calibrated. Certification
review was requested; behavior is **not auto-certified**.

## Evidence Chain

| Phase | Artifact |
|-------|----------|
| Design | `docs/native-runtime/append_existing_file_design.md` |
| Fixtures | 8 append matrix fixtures + historical `file_append_unsupported.exe` |
| Implementation | `alma_bridge/native_runtime/shim/kernel32_shim.c` |
| Security | `tests/native_runtime/test_append_security.py` |
| Behavior | `tests/native_runtime/test_append_behavior.py` |
| Conformance | `tests/runtime/test_append_conformance.py` |
| Governance proposal | `tests/seed/governance_append_existing_file_proposal.json` |

## Supported Semantics

- `OPEN_EXISTING` + `FILE_APPEND_DATA` on workspace-relative paths
- Synchronous append-at-EOF via host `O_APPEND`
- Zero-length writes, repeated open/append/close cycles
- Unicode filenames within workspace

## Preserved Unsupported

- Overlapped / async I/O (`ERROR_NOT_SUPPORTED`)
- Shared handles and share modes
- Arbitrary host absolute paths
- Wine delegation for append

## Certification Disposition

Expected level: **behavior_tested / verified / calibrated** — not forced **certified**.
Human governance review required before registry promotion.
