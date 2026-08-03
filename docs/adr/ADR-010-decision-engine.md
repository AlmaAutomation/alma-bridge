# ADR-010: Decision Engine is Read-Only and Deterministic

## Status

Accepted — 2026-08-02

## Context

Alma Bridge exposes compatibility evidence through Graph, Knowledge, Regression,
Comparison, Advisor, and Ask Alma layers. Operators need **deterministic execution
plan recommendations** that synthesize multi-layer evidence without granting
execution authority, prefix mutation, or verification consumption.

The Decision Engine sits above existing read-only services and produces structured
recommendations for human review — not authorization to execute.

## Decision

Introduce `alma_bridge/decision/` as a read-only recommendation layer:

```
Compatibility Graph (summary via Knowledge)
        ↓
Compatibility Knowledge (aggregate)
        ↓
Regression Intelligence (comparison)
        ↓
Session Comparison (optional pairwise diff)
        ↓
AI Advisor (deterministic observations)
        ↓
Ask Alma (optional operator context)
        ↓
Decision Engine (deterministic plan recommendation)
        ↓
Recommendation only — human approval required
```

### 1. Non-authoritative — never influences execution

The Decision Engine **reads** composed outputs from existing read-only services. It
never:

- Imports or invokes the planner or orchestrator
- Mutates VerificationEngine state or outcomes
- Triggers graph ingestion on read paths
- Persists decision state
- Emits `ActionIntent` or remediation commands
- Auto-executes strategies or prefix mutations
- Consumes verification authority

### 2. Deterministic plan output

`DecisionEngine.build_plan(input)` evaluates fixed rules over structured evidence.
Same inputs and evidence snapshots produce identical `plan_id`, `recommendations`,
and `generated_at` (derived from evidence timestamps).

### 3. Required recommendation fields

Every `DecisionRecommendation` includes:

- `confidence` (`ConfidenceLevel` with level, score, factors)
- `constraints` (read-only boundary, no auto-execute, verification authority)
- `provenance` (`ProvenanceRef` citing upstream evidence)
- `human_approval_required=True` with explicit `approval_reasons`

When evidence is insufficient, the engine emits a `hold` recommendation with
`human_approval_required=True`.

### 4. Graph service boundary

`CompatibilityGraphService.graph_for_*` triggers idempotent ingestion side effects.
Phase 1 decision context derives graph-oriented summaries from the Knowledge profile
only (same pattern as Advisor ADR-006). Graph ingestion is **not** invoked on
decision GET/POST paths.

### 5. Prohibited dependencies

The decision package must not import:

- `alma_bridge.learning.orchestrator`
- `alma_bridge.session.verification_gateway`
- `alma_bridge.session.mutations`
- winetricks / remediation executors
- `ActionIntent`
- `GraphIngestionEngine` (directly)
- `session.services.planner` (for launching)

### 6. HTTP API

- `GET /bridge/decision/plan?session_id=...` (or `application_fingerprint=...`)
- `POST /bridge/decision/plan` with structured `DecisionInput`

Both endpoints are read-only with no side effects.

## Consequences

- Operators receive auditable, provenance-backed plan recommendations.
- Execution authority remains with BridgeOrchestrator and VerificationEngine.
- Boundary tests enforce forbidden imports and no graph ingestion on read paths.
- Future phases may add bounded narrative rendering; core rules remain deterministic.
