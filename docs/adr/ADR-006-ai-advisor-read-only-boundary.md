# ADR-006: AI Advisor is Read-Only and Deterministic in Phase 1

## Status

Accepted — 2026-07-28

## Context

Alma Bridge exposes compatibility evidence through Graph, Knowledge, and Regression
layers. Operators need **structured, provenance-backed explanations** of what Alma
knows without execution authority, strategy recommendations, or LLM inference.

Phase 1 establishes the advisor **contract** and a **deterministic explanation
engine** that consumes existing layer outputs. No network calls or LLM integration
are included in this phase.

## Decision

Introduce `alma_bridge/advisor/` as a read-only explanation layer:

```
Compatibility Graph (evidence-derived)
        ↓
Compatibility Knowledge (aggregate)
        ↓
Regression Intelligence (comparison)
        ↓
AI Advisor (deterministic explanation)
        ↓
Explanation only (Explorer)
```

### 1. Non-authoritative — never influences execution

The advisor **reads** composed outputs from Knowledge and Regression services. It
never:

- Imports or invokes the planner or orchestrator
- Mutates VerificationEngine state or outcomes
- Triggers graph ingestion on read paths
- Persists knowledge profiles or advisor state
- Emits `ActionIntent` or remediation commands
- Recommends strategies, dependencies, or fixes
- Performs network calls or LLM inference (Phase 1)

### 2. Deterministic explanations only

`DeterministicAdvisorEngine.explain(context)` uses template-based copy derived
from structured data. Every observation cites `KnowledgeEvidenceReference`
provenance from upstream layers.

### 3. Language policy

`policy.py` enforces forbidden prescriptive phrases (`Use wine_gui`, `Best strategy`,
`Requires VC++`, `Application is broken`, `Alma recommends`, etc.). Explanations
fail validation if policy is violated.

### 4. Graph service boundary (Phase 1)

`CompatibilityGraphService.graph_for_*` triggers idempotent ingestion side effects.
Phase 1 advisor context builds `graph_summary` from the knowledge profile only.
The graph service may be injected for future read-only summaries but is **not
invoked** on advisor GET paths.

### 5. Prohibited dependencies

The advisor package must not import:

- `alma_bridge.learning.orchestrator`
- `alma_bridge.session.verification_gateway`
- `alma_bridge.session.mutations`
- winetricks / remediation executors
- `ActionIntent`
- `GraphIngestionEngine` (directly)

### 6. Verification authority

Verified outcome language reflects Knowledge aggregation rules:
`aggregate_verification_passed` is the sole gate. Exit-code-only success must
never appear as verified in advisor copy.

## Consequences

- Positive: Operators receive traceable, policy-checked explanations in Explorer.
- Positive: Advisor contract is stable before any LLM integration in later phases.
- Negative: Graph-native phrasing is knowledge-derived until a read-only graph
  summary API exists without ingestion.

## References

- ADR-003: Compatibility Graph is non-authoritative
- ADR-004: Compatibility Knowledge aggregation
- ADR-005: Compatibility Regression Intelligence
