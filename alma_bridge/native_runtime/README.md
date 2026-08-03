# Native Alma Runtime — Design Structure (Phase 0)

This directory holds **design-only** documentation for a future native Windows PE
compatibility runtime. No loader implementation is claimed in Phase 0B.

## Purpose

Research and document how Alma Bridge could eventually execute PE binaries
without Wine, while preserving ADR-001 verification authority and the runtime
provider boundary (ADR-014).

## Proposed layout

```
native_runtime/
├── README.md           # This file
├── pe/                 # PE format parsing research
│   ├── headers.md      # DOS/COFF/optional header notes
│   └── imports.md      # Import table and thunk research
├── loader/             # Loader design
│   ├── mapping.md      # Virtual memory mapping strategy
│   └── relocations.md  # Base relocation handling
├── api/                # Win32 API surface research
│   └── kernel32.md     # Minimal console subset
└── conformance/        # Future native-vs-Wine baselines
    └── scenarios.md
```

## Milestones

See [docs/roadmap/native-alma-runtime.md](../../docs/roadmap/native-alma-runtime.md)
for Milestones 0–7.

## Boundary

- `NativeAlmaRuntime` in `alma_bridge/runtime/providers/native_alma.py` is
  **fail-closed** and experimental.
- No code here may import `VerificationGateway` or transition session lifecycle.
- VerificationEngine remains the sole success authority.

## Non-goals (Phase 0)

- Shipping a PE loader
- Replacing Wine in production paths
- Forking or vendoring Wine
