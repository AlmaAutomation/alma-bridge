# ADR-021: Runtime Certification Platform

## Status

Accepted — 2026-08-02

## Context

Native Runtime Engineering Platform v1 ([ADR-020](ADR-020-native-runtime-engineering-platform.md))
delivers per-API specifications, behavior suites, benchmarks, and read-only dashboards.
ACI Phases 1–4 provide calibration, governance, and behavior profiles. Evidence v2.0
aggregates compatibility bundles and timelines.

Operators still need to answer: **exactly which behaviors are certified, why, and how
confidence evolves over time** — not merely whether a Win32 symbol is exported.

## Decision

Introduce **Alma Verification & Certification Platform v1** under
`alma_bridge/certification/`:

### 1. Behavior-scoped certification levels

Certification is scoped per `(capability_id, behavior_id)`, never whole subsystems.
Levels progress deterministically from evidence:

`unverified` → `specified` → `behavior_tested` → `verified` → `calibrated` →
`governed` → `certified` → `production_ready`

Stale certifications become `requires_revalidation` — history is never deleted.

### 2. Deterministic criteria

`criteria.py` computes certification level from read-only evidence links. No AI/LLM,
no auto-promotion of governance registry, no guessing.

### 3. Compliance matrix

API × Behavior × Status × Coverage × Evidence count × Verification % × Regression
status × Governance level — built deterministically from engineering profiles and ACI.

### 4. Historical evolution

Append-only `CertificationRecord` entries track level transitions over time with
evidence references for every decision.

### 5. Stale detection

Regression, ABI change, benchmark degradation, failed verification, provider
implementation change, or registry change triggers `requires_revalidation` with reason.

### 6. Read-only HTTP API

Routes under `/bridge/certification/*` — GET only, no binary execution, no POST apply.

### 7. Explorer dashboard

Alma Explorer panel at `/certification` in almasysdet for certification timeline,
compliance matrix, stale items, and evidence links.

## Consequences

- Every implemented behavior is explainable with evidence references
- Certification never auto-promotes governance maturity
- Unsupported behaviors (e.g. `append_existing_file`, `overlapped_io`) show
  documented gaps, not false certification from symbol presence
- VerificationEngine authority and runtime selection remain unchanged

## References

- [runtime-certification.md](../architecture/runtime-certification.md)
- [ADR-020](ADR-020-native-runtime-engineering-platform.md)
- [ADR-018](ADR-018-capability-registry-governance.md)
