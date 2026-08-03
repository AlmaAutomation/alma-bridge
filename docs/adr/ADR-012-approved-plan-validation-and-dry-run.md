# ADR-012: Approved Plan Validation and Non-Executing Dry Run

## Status

Accepted — 2026-08-02

## Context

ADR-010 introduced the read-only Decision Engine. ADR-011 added human review,
approval binding via plan digest, and export artifacts. Operators now need to
**validate an approved plan** against current host inventory, policy, and
evidence **without launching applications or mutating system state**.

## Decision

Introduce `alma_bridge/decision_validation/` as an observational validation layer
above Decision Review:

```
Decision Engine (read-only plan)
        ↓
Decision Review (human approval gate)
        ↓
Decision Validation (approved plan dry-run)
        ↓
Export artifacts (optional, with non-execution disclaimer)
        ↓
No execution — execution_performed remains false
```

### 1. Validation binds to approved review

Every validation request references `plan_id`, `plan_digest`, and `review_id`.
Validation re-computes the canonical plan digest and compares it to the submitted
digest and the bound review record. Stale approvals produce `status=stale`.

### 2. Seven validation dimensions

1. **Plan integrity** — digest match, schema support, evidence resolution
2. **Application identity** — fingerprint match, executable path stat, no substitution
3. **Runtime feasibility** — provider inventory (Wine/Proton), architecture support
4. **Environment feasibility** — prefix stat when referenced; unknown fields indeterminate
5. **Policy feasibility** — PolicyGate simulation, approval ≠ mutation authority, campaign guards
6. **Verification readiness** — supported contract, explicit requirement
7. **Evidence freshness** — session resolution, contradictory evidence warnings

### 3. Non-executing dry-run invariants

Every `DecisionPlanDryRunReport` MUST include:

- `execution_performed: false`
- `mutations_performed: false`
- `mode: dry_run`
- Disclaimer: *No application was launched and no system state was changed.*

Dry-run permitted operations: read config, read outcomes, read runtime inventory,
inspect plan, resolve evidence refs, filesystem metadata (stat only), policy simulation.

Dry-run forbidden operations: launch executable, create/change prefixes, install
runtimes, registry writes, remediations, execution leases, session lifecycle transitions.

### 4. Append-only persistence

Validation reports are stored in SQLite (`decision_plan_validations`) with
insert-only semantics for auditability.

### 5. Prohibited dependencies

Same boundary as ADR-010/011. The decision_validation package must not import:

- `alma_bridge.learning.orchestrator`
- `alma_bridge.execution.runner`
- `alma_bridge.session.verification_gateway`
- `alma_bridge.session.mutations`
- planner execution services
- `ActionIntent`
- remediation executors

Policy simulation mirrors PolicyGate semantics without constructing `ActionIntent`.

### 7. Validation report status semantics

Status reduction follows strict precedence:

| Order | Status | Condition |
|------:|--------|-----------|
| 1 | `stale` | Approved digest no longer matches or approval TTL expired |
| 2 | `invalid` | Review is not approved, or blocking plan-integrity / identity checks fail |
| 3 | `blocked` | Other blocking feasibility checks fail (runtime, policy guard, verification) |
| 4 | `indeterminate` | Required environment information remains unknown |
| 5 | `valid` | All blocking checks pass and no required unknowns remain |

When `status=valid` and observational warnings exist, reports include `has_warnings=true`.
This preserves API compatibility without adding a new enum value.

**Severity vs status effect**

| Severity | Failed check effect |
|----------|---------------------|
| `blocking` | May produce `invalid` or `blocked` depending on category |
| `warning` | Surfaces in checks; may set `has_warnings=true` when status is `valid` |
| `info` | Non-status-bearing; informational only |

**Environment unknowns**

- *Optional legacy* fields (e.g. `LD_LIBRARY_PATH`) → warning only, do not force `indeterminate`
- *Required unknown* fields (unrecognized keys needed for feasibility) → `indeterminate`

Dry-run invariants hold for every status: `execution_performed=false`, `mutations_performed=false`.

### 8. HTTP API

- `POST /bridge/decision/plans/{plan_id}/validate`
- `GET /bridge/decision/plans/{plan_id}/validations`
- `GET /bridge/decision/plans/{plan_id}/validation/latest`

No execute endpoint is provided in this phase.

## Consequences

- Operators can dry-run validate approved plans with auditable check history.
- Validation remains strictly observational; execution authority stays outside this phase.
- Explorer UI surfaces validation status without Run/Execute/Apply controls.
- Stale approval is distinguishable from validation staleness via `approval_stale`.
