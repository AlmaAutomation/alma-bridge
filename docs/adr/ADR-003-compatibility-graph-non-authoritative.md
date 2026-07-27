# ADR-003: Compatibility Graph is Non-Authoritative and Evidence-Derived

## Status

Accepted — 2026-07-27

## Context

Alma Bridge accumulates durable compatibility evidence across execution sessions,
verification bindings, framework detections, and prefix manifest captures. Platform
surfaces need a **versioned, queryable knowledge representation** that connects
applications, sessions, strategies, and verification contracts without re-entering
execution authority.

Prior to this decision, evidence correlation relied on ad hoc `file_hash` lookups
and intelligence assessments. No persisted graph structure existed for traversing
compatibility relationships with explicit provenance on every edge.

## Decision

Introduce **Compatibility Graph Phase 1** as a read-only knowledge layer under
`alma_bridge/graph/`. It ingests **persisted evidence only**, materializes
versioned `GraphNode` and `GraphEdge` records with mandatory provenance, and
exposes read-only HTTP queries. Ingestion is **idempotent** and **append-only**:
conflicting evidence produces distinct edges; history is never silently overwritten.

### 1. Non-authoritative — never influences execution

Compatibility Graph **reads** persisted evidence and **materializes** graph
records. It never:

- Consumes graph results in the planner or orchestrator
- Reorders strategies or mutates prefixes
- Emits `ActionIntent` or invokes remediation
- Invokes `VerificationEngine` or `VerificationGateway`
- Performs AI inference or probabilistic guessing beyond cited evidence confidence

Graph output informs operators, Explorer, and future platform surfaces only.
**VerificationEngine remains the sole authority for success.**

### 2. Every edge requires provenance

Each `GraphEdge` must carry one or more `GraphProvenance` references
(`source_type`, `source_id`, `session_id`, `attempt_id`, `captured_at`,
`engine_version`). Edges without provenance are rejected at model validation time.

### 3. Evidence-derived edge rules

| Edge type | Source rule |
|-----------|-------------|
| `session_for_application` | Persisted session record with `file_hash` |
| `detected_framework` | Structured framework detection artifacts (scoped to session/attempt) |
| `launched_via` | Recorded attempt `strategy_id` |
| `verified_by` | **Only** when persisted `verification.passed is True` |
| `used_prefix_manifest` | Persisted manifest capture |
| `produced_evidence` | Attempt-level evidence records |
| `runtime_observed` | Manifest `base_runtime` observation — **not** `runtime_required` |

Exit-code success, attempt `success=1` without verification pass, and failed
verification **must not** create `verified_by` edges.

### 4. Prohibited dependencies

The graph package must not import:

- `alma_bridge.learning.orchestrator`
- `alma_bridge.session.verification_gateway`
- `alma_bridge.session.mutations`
- winetricks or runtime installer modules
- LLM or advisory inference loops

Graph ingestion may reuse read-only intelligence evidence assembly
(`EvidenceBundleBuilder`) and outcomes/profile store **reads** only.

### 5. Repository isolation

- `ReadOnlyGraphEvidenceAdapter` reads execution/outcome stores without writes.
- `GraphStore` writes only to `compatibility_graph_nodes` and
  `compatibility_graph_edges` tables — never mutates `bridge_sessions`,
  `bridge_attempts`, or profile execution tables on read paths.

### 6. Deterministic, stable identities

Node and edge IDs are derived from canonical SHA-256 payloads
(`compatibility_graph_v1` schema). Re-ingesting the same evidence produces
identical IDs. Conflicting evidence differs in scope or provenance fingerprint,
 producing distinct edge IDs.

### 7. Read-only HTTP API

Expose graph queries via:

- `GET /bridge/graph/applications/{fingerprint}`
- `GET /bridge/graph/sessions/{session_id}`
- `GET /bridge/graph/nodes/{node_id}`
- `GET /bridge/graph/edges/{edge_id}`

Return `404` when no evidence exists. Return `422` for malformed evidence.
No mutating endpoints.

## Consequences

### Positive

- Stable, versioned compatibility subgraphs (e.g. Code::Blocks application graph)
- Complete provenance trail on every relationship
- Safe platform substrate for Explorer and Knowledge Database without execution coupling
- Architecture tests enforce boundary invariants permanently

### Negative

- Graph is materialized on query (lazy idempotent ingestion) — no background indexer yet
- Application correlation still keyed on `file_hash` until richer program identity ingestion
- `runtime_required` edges deferred to a future phase

## Related artifacts

- `alma_bridge/graph/`
- `alma_bridge/api/graph_routes.py`
- `tests/graph/`
- [ADR-001: Authoritative Bridge Lifecycle](ADR-001-authoritative-bridge-lifecycle.md)
- [ADR-002: Compatibility Intelligence Boundary](ADR-002-compatibility-intelligence-boundary.md)
- [Full-suite test isolation triage](../reviews/full-suite-test-isolation-triage.md)
