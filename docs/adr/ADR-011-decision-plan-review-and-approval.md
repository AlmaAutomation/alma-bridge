# ADR-011: Decision Plan Review, Approval, and Export

## Status

Accepted — 2026-08-02

## Context

ADR-010 introduced the read-only Decision Engine, which produces deterministic
execution plan recommendations. Operators need a **human review workflow** to
approve, reject, or request revision of plans before any future execution phase —
without granting execution authority in this phase.

## Decision

Introduce `alma_bridge/decision_review/` as an append-only review layer above the
read-only Decision Engine:

```
Decision Engine (read-only plan)
        ↓
Decision Review (human approval gate)
        ↓
Export artifacts (JSON / Markdown)
        ↓
No execution — execution_status remains not_executed
```

### 1. Approval binds to plan integrity

Every review records `plan_id`, `plan_version`, and `plan_digest`. The digest is
computed from canonical plan serialization **excluding** `generated_at`. When the
plan content changes, prior approvals become stale.

### 2. Append-only persistence

Reviews and exports are stored in SQLite tables (`decision_plan_reviews`,
`decision_plan_exports`) with insert-only semantics for auditability.

### 3. Approval policy (8 requirements)

Approval is permitted only when:

1. Non-empty evidence references exist in the plan
2. Verification authority is acknowledged for post-execution outcomes
3. No unsupported runtime requirement is asserted
4. No automatic remediation command is present
5. No direct mutation instruction is present
6. Confidence is present but does not substitute for missing evidence
7. Reviewer acknowledges all listed risks (warning/critical severity)
8. Submitted `plan_digest` matches the current canonical plan

Reject and needs-revision decisions skip approval policy but still bind to the
current plan digest.

### 4. Export disclaimer

All exported artifacts include:

> This artifact does not authorize or perform execution.

`execution_status` is always `not_executed` in this phase.

### 5. Prohibited dependencies

Same boundary as ADR-010. The decision_review package must not import:

- `alma_bridge.learning.orchestrator`
- `alma_bridge.execution.runner`
- `alma_bridge.session.verification_gateway`
- `alma_bridge.session.mutations`
- planner execution services
- `ActionIntent`
- remediation executors

### 6. HTTP API

- `GET /bridge/decision/plans/{plan_id}`
- `GET /bridge/decision/plans/{plan_id}/reviews`
- `GET /bridge/decision/plans/{plan_id}/review/latest`
- `POST /bridge/decision/plans/{plan_id}/reviews`
- `POST /bridge/decision/plans/{plan_id}/export` (json, markdown)

Plan rebuild requires `session_id` or `application_fingerprint` query parameters.

## Consequences

- Operators can audit human decisions with provenance-backed evidence references.
- Stale approvals are detectable when plan digests change.
- Execution authority remains outside this phase; exports are informational only.
- Explorer UI surfaces review workflow without execute/apply controls.
