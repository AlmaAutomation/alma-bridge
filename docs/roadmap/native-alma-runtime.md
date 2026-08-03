# Native Alma Runtime Roadmap

Design-only roadmap for a future native PE compatibility runtime. **No loader
implementation is claimed in Phase 0B.**

## Milestone 0 — Boundary and audit (complete in Phase 0B)

- Runtime dependency audit
- ADR-014 provider boundary
- `NativeAlmaRuntime` fail-closed stub
- Design structure under `alma_bridge/native_runtime/`

## Milestone 1 — PE format research

- Document DOS/COFF/optional header parsing requirements
- Import table and thunk research notes under `native_runtime/pe/`

## Milestone 2 — Loader design

- Virtual memory mapping strategy
- Base relocation handling
- Design docs under `native_runtime/loader/`

## Milestone 3 — Minimal console subset

- kernel32/ntdll API surface research for console PE
- Capability declaration: `pe_console` moves from `unknown` to `partial`

## Milestone 4 — Conformance harness

- Native-vs-Wine baseline scenarios
- Integration with `runtime/conformance/`

## Milestone 5 — Isolated prototype

- Standalone loader prototype (not wired to orchestrator)
- Fail-closed by default; opt-in experimental flag

## Milestone 6 — Provider integration

- `NativeAlmaRuntime.prepare/launch` behind feature flag
- Planner bridge selects native provider only when explicitly requested

## Milestone 7 — Production evaluation

- Conformance gate: `functionally_equivalent` on pilot catalog
- VerificationEngine remains sole success authority
- Wine remains available; no fork

## Non-goals

- Replacing Wine in production without conformance evidence
- Forking or vendoring Wine
- Moving verification authority to runtime providers

## References

- [alma-compatibility-runtime.md](../architecture/alma-compatibility-runtime.md)
- [ADR-014](../adr/ADR-014-compatibility-runtime-provider-boundary.md)
- `alma_bridge/native_runtime/README.md`
