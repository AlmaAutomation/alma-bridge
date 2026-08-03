# Native Alma Runtime Roadmap

Roadmap for the native PE compatibility runtime. **Milestone 1** delivers an
experimental console PE loader behind feature flags.

## Milestone 0 — Boundary and audit (complete)

- Runtime dependency audit
- ADR-014 provider boundary
- `NativeAlmaRuntime` fail-closed stub
- Design structure under `alma_bridge/native_runtime/`

## Milestone 1 — Console loader prototype (complete)

- User-space PE parser and eligibility checks
- Isolated worker subprocess execution
- Kernel32 API shim (simulation + optional C `.so`)
- Allow-listed conformance fixtures
- `POST /bridge/runtime/native/inspect` read-only API
- ADR-015, threat model, conformance docs
- Feature flags: `native_runtime_enabled`, `allow_experimental_runtimes`

## Milestone 2 — Loader hardening

- Full IAT patch and native entry invocation
- Base relocation coverage for ASLR images
- PE32 worker on x86_64 hosts

## Milestone 3 — Minimal console subset

- Expanded kernel32 surface
- Capability: `pe_console` partial → supported with evidence

## Milestone 4 — Conformance harness

- Native-vs-Wine baseline on full fixture catalog
- Integration with `runtime/conformance/` launch path

## Milestone 5 — Isolated prototype

- Standalone loader prototype (not wired to orchestrator)
- Fail-closed by default; opt-in experimental flag

## Milestone 6 — Provider integration

- `NativeAlmaRuntime.prepare/launch` in orchestrator `/bridge/run`
- Planner selects native provider when explicitly requested

## Milestone 7 — Production evaluation

- Conformance gate: `functionally_equivalent` on pilot catalog
- VerificationEngine remains sole success authority
- Wine remains available; no fork

## Non-goals

- Replacing Wine in production without conformance evidence
- Forking or vendoring Wine
- Moving verification authority to runtime providers

## References

- [native-alma-runtime-m1.md](../architecture/native-alma-runtime-m1.md)
- [ADR-015](../adr/ADR-015-native-console-runtime-milestone-1.md)
- [alma-compatibility-runtime.md](../architecture/alma-compatibility-runtime.md)
- ADR-014
