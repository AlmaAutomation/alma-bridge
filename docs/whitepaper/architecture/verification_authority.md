# Verification Authority — Architecture Deep-Dive

**Status:** As-built (ADR-001, enforced by tests)  
**Companion:** [verification_authority.mmd](../diagrams/verification_authority.mmd)

## Problem addressed

Before ADR-001, multiple subsystems could treat subprocess exit codes, detached GUI processes, route-level HTTP success, or prior-success lookups as compatibility success. Session `success=1` could diverge from verified outcomes.

## Authoritative components

| Component | File | Role |
|-----------|------|------|
| BridgeOrchestrator | `learning/orchestrator.py` | Sole driver of bridge session lifecycle for `/bridge/run` |
| SessionLifecycleManager | `session/lifecycle.py` | Transactional state machine; optimistic concurrency |
| DefaultVerificationEngine | `session/services/verification.py` | Routes to installer/launcher/process verifiers; owns aggregate policy |
| VerificationGateway | `session/verification_gateway.py` | Runs OBSERVING→VERIFYING; calls `declare_verified_session_success()` |
| PolicyGate | `session/policy.py` | Evaluates `ActionIntent` before mutations |
| prefix_lock + run_prefix_mutation | `session/prefix_lock.py`, `session/mutations.py` | Serialized prefix writes |

## Lifecycle states (simplified)

```
PLANNING → EXECUTING → OBSERVING → VERIFYING → SUCCEEDED
                              ↘ CLASSIFYING → (retry) → EXECUTING
```

`SUCCEEDED` is reachable **only** through `VerificationGateway.declare_verified_session_success()`.

## Aggregate success policy

`session/stop_on_success_verification.py` defines `aggregate_verification_passed()` — a pure predicate over verification JSON using policy version `bridge_aggregate_v1` with phase-specific required checks (`native`, `install`, `launcher`).

**Critical invariant:** `exit_code == 0`, attempt `success=1` without verification pass, and route-level success are **not** terminal success signals (ADR-001, ADR-002).

Read-only layers `knowledge` and `comparison` import this predicate to align read-path metrics with write-path authority — documented as a layering smell, not a violation (`READ_ONLY_BOUNDARIES.md` §3).

## Verification persistence

Verification results are persisted on the attempt row as `verification_json`. Persistence failure fails closed (ADR-001). Verifier exceptions become structured failure evidence; they never produce `SUCCEEDED`.

## Prohibited patterns (ADR-001)

1. `finalize_session(success=True)` outside VerificationGateway
2. Direct `SUCCEEDED` transitions outside verified-success path
3. Child bridge sessions for internal escalation (same `session_id` preserved)
4. Recursive BridgeOrchestrator in route executors
5. Unguarded prefix mutation
6. Prior-success lookup bypassing current verification

## Session lease

`SessionLeaseManager` (`session/lease.py`) acquires at `/bridge/run` start, renews on transitions. Concurrent workers without lease must not advance lifecycle.

## Scope exclusion

Compliance autopilot and host modernization apply paths are **not** wrapped in ADR-001 bridge lifecycle (ADR-001 migration notes). They have separate dry-run and approval semantics (`SECURITY.md`).

## Tests

| Test file | Asserts |
|-----------|---------|
| `tests/test_verification_authority.py` | Gateway exclusivity, no stray finalize_success |
| `tests/test_orchestrator_authority.py` | Orchestrator owns transitions |
| `tests/test_architecture_invariants.py` | Cross-cutting invariants |
| Read-only boundary tests | No import of `verification_gateway` in platform tier |

## Related documents

- [ADR-001](../../adr/ADR-001-authoritative-bridge-lifecycle.md)
- [LAYER_DIAGRAM.md](../../architecture/LAYER_DIAGRAM.md) §4
