# ADR-004: Compatibility Knowledge Aggregation is Non-Authoritative and Evidence-Derived

## Status

Accepted — 2026-07-28

## Context

Alma Bridge accumulates compatibility evidence across multiple execution sessions
for the same application fingerprint. Operators and Explorer need **aggregated,
cross-session compatibility knowledge** — framework observations, launch strategy
outcomes, verification contracts, and runtime observations — without re-entering
execution authority or triggering graph ingestion side effects.

Prior to this decision, per-session intelligence assessments and graph subgraphs
existed, but no deterministic aggregation surfaced session-level statistics,
competing framework observations, or strategy success rates with explicit
provenance on every claim.

## Decision

Introduce **Compatibility Knowledge Phase 1** as a read-only aggregation layer under
`alma_bridge/knowledge/`. It assembles persisted evidence via `EvidenceBundleBuilder`,
aggregates across all sessions for an application fingerprint, and exposes a
read-only HTTP query. Aggregation is **deterministic** and **non-destructive**:
competing frameworks are preserved as conflicts; history is never collapsed into
a single "winner."

### 1. Non-authoritative — never influences execution

Compatibility Knowledge **reads** persisted evidence and **aggregates** profile
records. It never:

- Consumes knowledge results in the planner or orchestrator
- Reorders strategies or mutates prefixes
- Emits `ActionIntent` or invokes remediation
- Invokes `VerificationEngine` or `VerificationGateway`
- Triggers graph ingestion on read paths
- Performs AI inference beyond cited evidence confidence

Knowledge output informs operators and Explorer only.
**VerificationEngine remains the sole authority for success.**

### 2. Success metrics use authoritative verification only

Session and strategy success metrics count **only** when
`aggregate_verification_passed({"verification": ...})` is True. Exit-code success,
attempt `success=1` without verification pass, and route-level HTTP success must
not inflate verified success counts.

### 3. Evidence classifications

Framework observations use deterministic classifications:

| Classification | Rule |
|----------------|------|
| `observed` | Single observation of this framework |
| `repeated` | Two or more observations, no competing frameworks |
| `conflicting` | Multiple distinct frameworks observed for the same application |

There is no `confirmed_required` classification. Knowledge does not assert
requirements — only observations.

### 4. Runtime observations

Runtime records use **runtime_observed** semantics (attempt `runtime` field and
manifest `base_runtime` captures). There is no `runtime_required` edge or
classification in this layer.

### 5. Conflicts preserved

When multiple frameworks are detected across sessions, all frameworks remain in
`observed_frameworks` and a `conflicts` entry records competing observations with
evidence for each side. Competing frameworks are **not** collapsed.

### 6. Prohibited dependencies

The knowledge package must not import:

- `alma_bridge.learning.orchestrator`
- `alma_bridge.session.verification_gateway`
- `alma_bridge.session.mutations`
- winetricks or runtime installer modules
- LLM or advisory inference loops
- `GraphIngestionEngine` on read paths

Knowledge may reuse read-only intelligence evidence assembly
(`EvidenceBundleBuilder`) and outcomes/profile store **reads** only.

### 7. Repository isolation

- `ReadOnlyKnowledgeEvidenceAdapter` reads execution/outcome stores without writes.
- No knowledge-specific persistence tables are required in Phase 1; profiles are
  computed on read from persisted session evidence.

### 8. HTTP API

- `GET /bridge/knowledge/applications/{fingerprint}` — returns
  `CompatibilityKnowledgeProfile`
- GET-only; 404 when no evidence; 422 on malformed evidence
- Must **not** trigger graph ingestion

## Consequences

- Explorer can show cross-session compatibility summaries with provenance links.
- Future KB persistence (Phase 2) can cache aggregated profiles without changing
  the non-authoritative contract.
- Boundary tests enforce the same forbidden-import and GET-only constraints as
  intelligence and graph packages.

## References

- [ADR-003: Compatibility Graph is Non-Authoritative](./ADR-003-compatibility-graph-non-authoritative.md)
- [ADR-002: Compatibility Intelligence Boundary](./ADR-002-compatibility-intelligence-boundary.md)
