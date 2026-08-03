# Native Alma Runtime — Milestone 1

Isolated user-space PE console loader with kernel32 shim. See
[docs/architecture/native-alma-runtime-m1.md](../../docs/architecture/native-alma-runtime-m1.md).

## Boundary

- Execution occurs in **worker subprocess** only.
- No `VerificationGateway` imports.
- Feature flags: `native_runtime_enabled`, `allow_experimental_runtimes` (default false).

## Build fixtures

```bash
tests/fixtures/native_runtime/build_fixtures.sh
```

## Package layout

```
native_runtime/
├── pe/          PE parser
├── loader/      Image mapping and entry
├── process/     Environment, handles, exit
├── console/     stdout/stderr capture
├── filesystem/  Sandboxed paths
├── api/         kernel32 simulation fallback
├── shim/        C ms_abi shims (optional)
├── runtime.py   Orchestration
└── worker.py    Subprocess entry
```
