# Native Execution Proof (Milestone 2)

## Goal

Demonstrate that fixture stdout/exit behavior originates from PE machine code,
not Python fixture-name simulation tables.

## Mandatory anti-simulation tests

`tests/native_runtime/test_anti_simulation.py` (8 tests):

1. Real `hello64.exe` — evidence fields, no hardcoded shim string
2. Rebuilt fixture with custom message — output changes without runtime code change
3. Renamed fixture — same behavior via digest manifest
4. Simulation only when `use_simulation=True`
5. `ALMA_NATIVE_SIMULATION=1` diagnostic mode
6. Evidence fields on every native run
7. Forced relocation delta via Python `map_pe_image(load_base=...)`
8. Production path fails closed when shim missing

## Conformance

`native_vs_wine_hello64` scenario compares Wine baseline to native candidate on
built `tests/fixtures/native_runtime/bin/hello64.exe`.

## Build

```bash
tests/fixtures/native_runtime/build_fixtures.sh
```

Requires `x86_64-w64-mingw32-gcc` for PE fixtures and host `gcc` for the shim.
