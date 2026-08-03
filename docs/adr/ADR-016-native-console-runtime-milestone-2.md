# ADR-016: Native Console Runtime — Milestone 2 (Real PE64 Execution)

## Status

Accepted

## Context

Milestone 1 (ADR-015) delivered PE inspection, fixture simulation, and worker
subprocess isolation. M1 intentionally simulated fixture output in
`alma_native_run_pe` when full IAT patching was incomplete.

## Decision

1. **Real execution**: PE64 images are `mmap`'d, DIR64 relocations applied,
   kernel32 IAT patched with `ms_abi` shims, and the PE entrypoint invoked.
2. **No production simulation**: when `libalma_native_shim.so` is present, the
   runtime executes mapped machine code. Simulation is allowed only when
   `use_simulation=True` or `ALMA_NATIVE_SIMULATION=1`.
3. **Evidence fields**: worker IPC returns `simulation_used`, `entrypoint_invoked`,
   `native_execution_mode`, `load_base`, and `binary_digest`.
4. **Fixture manifest**: allow-list supplement keyed by SHA-256 digest permits
   renamed allow-listed fixtures.
5. **Worker subprocess only** — unchanged from M1; FastAPI never maps PE images.
6. Provider version bump to `0.2.0-m2`; `use_simulation=False` in launch jobs.

## Consequences

- Anti-simulation tests can prove stdout comes from PE machine code, not Python
  fixture tables.
- UTF-16LE wide-string ABI requires explicit UTF-16 handling in shims (Linux
  `wchar_t` is 32-bit).
- Conformance harness compares Wine vs native on built `hello64.exe`.

## References

- [native-pe64-loader.md](../architecture/native-pe64-loader.md)
- [native-shim-abi.md](../architecture/native-shim-abi.md)
- [native-execution-proof.md](../testing/native-execution-proof.md)
- ADR-015
