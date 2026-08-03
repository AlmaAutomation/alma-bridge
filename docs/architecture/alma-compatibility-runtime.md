# Alma Compatibility Runtime

Phase 0B introduces a **compatibility runtime layer** between the compatibility
planner and host execution backends (Wine, Proton, container).

## Goals

- Unified provider contract without changing orchestrator behavior
- Deterministic capability declarations
- Read-only provider inventory API
- Foundation for future runtime independence (design-only for native Alma)

## Architecture

```
compatibility/planner.py
        │
        ▼
runtime/planner_bridge.py  ──► runtime/selection.py
        │                              │
        ▼                              ▼
runtime/registry.py ◄──── runtime/providers/{wine,proton,container,native_alma}.py
        │
        ▼
execution/runner.py  (unchanged authority path via orchestrator)
```

## Provider registry

`RuntimeRegistry` registers providers in deterministic order at startup:

1. `wine`
2. `proton`
3. `container`
4. `native_alma` (experimental, fail-closed)

Duplicate provider IDs raise `DuplicateProviderError`.

## Import boundary

Providers may import hardware profiling and command-building helpers.
Providers must not import VerificationGateway or orchestrator modules.

See [runtime-dependency-audit.md](./runtime-dependency-audit.md).

## API

`GET /bridge/runtime/providers` — read-only inventory with capability states.

## Related documents

- [runtime-capability-model.md](./runtime-capability-model.md)
- [runtime-conformance.md](./runtime-conformance.md)
- [ADR-014](../adr/ADR-014-compatibility-runtime-provider-boundary.md)
