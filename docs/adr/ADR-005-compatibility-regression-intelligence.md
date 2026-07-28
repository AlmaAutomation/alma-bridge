# ADR-005: Compatibility Regression Intelligence is Read-Only Profile Comparison

## Status

Accepted — 2026-07-28

## Context

Alma Bridge aggregates cross-session compatibility knowledge into
`CompatibilityKnowledgeProfile` snapshots (ADR-004). Operators need to compare a
**comparison session** against a **baseline** derived from prior sessions for the
same application fingerprint — detecting verified-outcome regressions, strategy
rate changes, framework evidence shifts, and new conflicts — without triggering
execution, ingestion, or advisory inference.

## Decision

Introduce **Compatibility Regression Intelligence Phase 1** as a thin comparison
layer under `alma_bridge/regression/`. It reuses `EvidenceBundleBuilder`,
`KnowledgeAggregationEngine`, and `ReadOnlyKnowledgeEvidenceAdapter` to build:

1. **Baseline profile** — aggregate evidence excluding comparison session X
2. **Current profile** — aggregate evidence including all sessions
3. **Regression report** — `RegressionDiffEngine.compare(before, after)`

### 1. Pure diff engine

`RegressionDiffEngine.compare(before, after)` is **pure**: no SQL, no
`OutcomesStore` writes, no graph ingestion, no `VerificationEngine`, no
orchestrator/planner, no filesystem mutation.

### 2. Regression vs change semantics

| Type | Language |
|------|----------|
| `VERIFIED_SUCCESS_TO_VERIFIED_FAILURE` | "compatibility regression" |
| `FRAMEWORK_CHANGED` | "framework evidence changed" (not failure) |
| `VERIFICATION_CONTRACT_CHANGED` | "verification contract changed" |
| `RUNTIME_OBSERVATION_CHANGED` | "runtime observation changed" |
| `NEW_CONFLICT` | "new conflicting evidence" |
| `STRATEGY_SUCCESS_RATE_DROPPED` | factual rate change (not "broken") |

Every finding requires non-empty `previous_state.evidence_references` and
`current_state.evidence_references`. Top-level `evidence_references` is the
deterministic union of before and after refs.

### 3. Baseline exclusion and session ordering

For comparison session X:

- Baseline = aggregate(bundle excluding X)
- Current = aggregate(bundle including all sessions)
- Session ordering uses `(started_at, session_id)` — never DB row order
- Default comparison session = latest by that ordering

First session (no baseline): valid report, zero findings, explicit insufficient-baseline summary.

### 4. Strategy rate detection constants

- `MIN_BASELINE_ATTEMPTS = 3`
- `MIN_RATE_DELTA = 0.25`
- `SUCCESS_RATE_DROP_THRESHOLD = 0.75`

### 5. Prohibited dependencies

Same forbidden imports as knowledge: orchestrator, verification gateway,
session mutations, winetricks, `ActionIntent`, graph ingestion on read paths.

### 6. HTTP API (GET only)

- `GET /bridge/regression/applications/{fingerprint}?session_id=optional`
- `GET /bridge/regression/sessions/{session_id}`

Must not trigger graph ingestion.

## Consequences

- Explorer can show session-scoped regression findings with provenance.
- Future remediation/advisor layers remain separate; regression does not recommend actions.
- Boundary tests mirror knowledge architecture constraints.

## References

- [ADR-004: Compatibility Knowledge Aggregation](./ADR-004-compatibility-knowledge-aggregation.md)
- [ADR-003: Compatibility Graph is Non-Authoritative](./ADR-003-compatibility-graph-non-authoritative.md)
