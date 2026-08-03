# ADR-019: Capability-Guided Runtime Expansion Planning

## Status

Accepted — 2026-08-02

## Context

ACI Phases 1–3 provide static PE analysis, prediction calibration, and
human-gated capability registry governance ([ADR-017](ADR-017-compatibility-prediction-calibration.md),
[ADR-018](ADR-018-capability-registry-governance.md)). Calibration and
governance measure and promote capability maturity but do **not** answer
which narrowly scoped engineering work would unlock the most verified
compatibility value next.

Operators need **deterministic engineering priorities** for expanding
NativeAlmaRuntime — advisory plans only, with no automatic implementation,
registry mutation, or execution.

## Decision

Introduce **Runtime Expansion Planning** under
`alma_bridge/compatibility_intelligence/expansion/`:

### 1. Engineering candidates (bounded scope)

Each `RuntimeExpansionCandidate` is scoped to a single provider, capability,
and optional behavior (e.g. `filesystem.basic_io / append_existing_file /
native_alma / PE64 console`). Candidates are **not** approved or implemented
by the planner.

### 2. Demand model (observed, deduplicated)

Deterministic counts from existing evidence only:

- Distinct binary digests requiring the capability/behavior
- Distinct application fingerprints
- Blocked native eligibility decisions
- False positives attributable to missing behavior
- Verified Wine successes using the same requirement

Repeated sessions for one binary do **not** inflate demand. Recency is
reported separately from normalized scores.

### 3. Bounded impact model

Impact language is strictly bounded:

- "Could remove the currently identified blocker for N analyses"
- **Not** "Will make N applications compatible"

Estimates cover binaries moving ineligible→eligible, behavior coverage
increase, and calibration gaps potentially resolved.

### 4. Complexity and risk (dimensions preserved)

- Engineering complexity: trivial → very_high with factor explanations
- Security risk: explicit categories (filesystem escape, code loading, etc.)
- Semantic risk: explicit categories (broad behavior surface, async callbacks, etc.)

Risk is **not** collapsed into a single opaque score without category detail.

### 5. Deterministic priority ranking

Composite priority preserves all dimensions: demand, bounded impact,
engineering cost, security risk, semantic risk, evidence quality,
testability.

Hard exclusions: kernel drivers, anti-cheat, arbitrary DLL loading,
unbounded process creation, undocumented scope, no reproducible test fixture.

### 6. Read-only API

GET endpoints only — no POST apply, no execution, no registry mutation,
no provider selection change, no code generation.

## Consequences

- Human engineering judgment remains authoritative
- Plans are reproducible and auditable via evidence digest
- Explorer surfaces demand, impact, complexity, and risk distinctly
- Registry maturity is never mutated by expansion planning

## References

- [runtime-expansion-planning.md](../architecture/runtime-expansion-planning.md)
- [runtime-expansion-ranking.md](../testing/runtime-expansion-ranking.md)
- ADR-017, ADR-018
