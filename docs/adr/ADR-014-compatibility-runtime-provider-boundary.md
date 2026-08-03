# ADR-014: Compatibility Runtime Provider Boundary

## Status

Accepted

## Context

Alma Bridge executes Windows PE and mixed-format binaries through Wine, Proton,
and container sandboxes. Execution logic is spread across `execution/`,
`compatibility/planner.py`, and `learning/orchestrator.py`. There is no unified
provider contract or capability model.

Phase 0B introduces `alma_bridge/runtime/` to define provider boundaries without
changing orchestrator behavior or VerificationEngine authority.

## Decision

1. Introduce `CompatibilityRuntimeProvider` protocol with lifecycle methods:
   `capabilities`, `inspect`, `prepare`, `launch`, `observe`, `terminate`,
   `teardown`.
2. Register providers at startup via deterministic `RuntimeRegistry` — duplicate
   IDs rejected, no dynamic untrusted loading.
3. Providers **must not** import `VerificationGateway`, `BridgeOrchestrator`,
   or session lifecycle mutation modules.
4. `RuntimeCapabilities` declares capability states:
   `supported`, `partial`, `unsupported`, `unknown`, `delegated`.
5. Planner integration is **additive**: `runtime/planner_bridge.py` annotates
   existing strategy plans with `runtime_provider_id` without changing strategy
   IDs.
6. Expose read-only `GET /bridge/runtime/providers` inventory.
7. `NativeAlmaRuntime` is experimental and fail-closed; native loader work stays
   design-only under `native_runtime/`.

## Consequences

- Wine, Proton, and container paths remain the production execution backends.
- Orchestrator continues to call `execution/runner.py` directly in Phase 0B.
- Runtime providers are thin adapters preparing for future decoupling.
- Conformance foundation enables baseline comparison without claiming Wine
  independence.

## References

- [runtime-dependency-audit.md](../architecture/runtime-dependency-audit.md)
- [alma-compatibility-runtime.md](../architecture/alma-compatibility-runtime.md)
- ADR-001 (verification authority unchanged)
