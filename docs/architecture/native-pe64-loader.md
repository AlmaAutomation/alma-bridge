# Native PE64 Loader (Milestone 2)

## Overview

The C loader in `alma_bridge/native_runtime/shim/pe_loader.c` maps PE64 console
fixtures into an anonymous `mmap` region, applies relocations, patches the
kernel32 import address table (IAT), and invokes the PE entrypoint.

## Load sequence

1. Parse PE64 headers from raw bytes (DOS → COFF → optional → sections).
2. `mmap(PROT_READ|PROT_WRITE|PROT_EXEC)` sized to `SizeOfImage`.
3. Copy headers and section raw data; BSS is zero-filled.
4. Apply `IMAGE_REL_BASED_DIR64` relocations with
   `delta = (uintptr_t)map - ImageBase`.
5. Patch IAT: allow `KERNEL32.dll` imports only; resolve named exports to
   `ms_abi` shim trampolines.
6. Call entry at `map + AddressOfEntryPoint`; `ExitProcess` returns via
   `siglongjmp` to the runner.

## Python integration

- `loader/image.py` — optional `load_base` override for forced relocation tests
  in Python-mapped buffers (conformance / unit tests).
- `loader/entrypoint.py` — `alma_native_load_and_run(pe_bytes, len, override)`
  with UTF-16LE command line and env block init.

## Security

Execution occurs only inside the worker subprocess. See
[native-runtime-threat-model.md](../security/native-runtime-threat-model.md).
