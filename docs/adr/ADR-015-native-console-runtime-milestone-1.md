# ADR-015: Native Console Runtime — Milestone 1

## Status

Accepted

## Context

Phase 0B established the compatibility runtime provider boundary (ADR-014) with
`NativeAlmaRuntime` fail-closed. Milestone 1 delivers a **narrow, experimental**
user-space PE loader for **console subsystem** binaries with **kernel32-only**
imports, executed in an **isolated worker subprocess**.

## Decision

1. **Approach A**: Alma-owned PE loader + Win32 API shim; no Wine/QEMU/Unicorn delegation.
2. PE32+ x64 runs on x86_64 hosts via `mmap` + patched IAT + `ms_abi` C shims.
3. PE32 x86 requires a 32-bit-capable worker; otherwise fail-closed with reason.
4. Execution never occurs inside FastAPI/Uvicorn — worker subprocess only.
5. Feature flags (`native_runtime_enabled`, `allow_experimental_runtimes`) gate all
   non-inspect operations; default **false**.
6. Eligibility: allow-listed fixture basenames **or** strict PE checks (console
   subsystem, no TLS/delay imports, import DLL allow-list).
7. VerificationEngine remains sole success authority; runtime providers do not
   import `VerificationGateway`.
8. Conformance harness may compare Wine baseline vs native candidate on fixtures.

## Consequences

- `pe_console` moves to `partial` when flags enabled and host eligible.
- Orchestrator full wiring deferred; conformance runner uses provider launch path first.
- Production PE execution continues through Wine/Proton/container until M7 evaluation.

## References

- [native-alma-runtime-m1.md](../architecture/native-alma-runtime-m1.md)
- [native-runtime-threat-model.md](../security/native-runtime-threat-model.md)
- ADR-014, ADR-001
