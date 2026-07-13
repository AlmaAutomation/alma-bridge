# ADR-001: Authoritative Bridge Lifecycle and Verification Boundary

## Status

Accepted — 2026-07-13

## Context

Alma Bridge previously allowed multiple subsystems to infer compatibility success from
proxy signals: subprocess exit codes, detached GUI processes, installer log completion,
route execution results, prior-success lookups, and inline application-specific checks.
Session persistence (`success=1`) and lifecycle state were decoupled. Route services could
construct `BridgeOrchestrator`, and escalation could spawn orphan child sessions.

This produced fragmented authority, weak lineage, and false-positive compatibility outcomes.

## Decision

`BridgeOrchestrator` is the sole lifecycle owner for `/bridge/run`. No bridge session or
attempt may be marked successful unless:

1. The orchestrator enters `VERIFYING`
2. The injected `VerificationEngine` returns a structured `VerificationResult`
3. The versioned aggregate success policy evaluates to `passed=True`
4. The verification result is persisted on the attempt
5. `VerificationGateway.declare_verified_session_success()` transitions `VERIFYING → SUCCEEDED`
   and calls `finalize_session(success=True)`

All other success-like signals are evidence inputs to `VerificationEngine`, never terminal
authorities.

## Authoritative lifecycle owner

| Component | Role |
|---|---|
| `BridgeOrchestrator` | Sole driver of bridge session lifecycle for `/bridge/run` |
| `SessionLifecycleManager` | Transactional state machine; only orchestrator may transition states |
| `VerificationGateway` | Sole path to `SUCCEEDED` and `finalize_session(success=True)` |
| `VerificationEngine` | Aggregates execution evidence; owns verification semantics |
| `PolicyGate` | Evaluates `ActionIntent`; no dependency on `BridgeRequest` |
| `SessionLeaseManager` | DB-backed lease; only lease holder should advance lifecycle |
| `prefix_lock` + `run_prefix_mutation` | Prefix mutations require policy approval and flock ownership |

## Verification authority

- Every execution attempt produces `ExecutionEvidence`
- `DefaultVerificationEngine.verify_execution()` routes to installer, launcher, or process verifiers
- Aggregate policy `bridge_aggregate_v1` defines required checks per phase (`native`, `install`, `launcher`)
- Verification persistence failure fails closed
- Verifier exceptions become structured failure evidence; they never produce `SUCCEEDED`

## Policy boundary

- All mutations are expressed as `ActionIntent`
- `PolicyGate.evaluate()` must approve before execution
- Escalation routes return `requires_bridge_retry`; they do not finalize sessions
- Route-level `success` is not session-level success

## Session lease

- `SessionLeaseManager.acquire()` runs at `/bridge/run` start
- Lease is renewed on each lifecycle transition
- Concurrent workers without the lease cannot drive lifecycle progression

## Resource locking

- Prefix mutations use stable `fcntl.flock` lock files under `{data_dir}/locks/`
- Lock files are never deleted; kernel ownership is authoritative
- `run_prefix_mutation()` enforces policy then lock, in that order

## Escalation lineage

- Escalation preserves the same `session_id`
- No orphan child bridge sessions for internal retries
- Escalation metadata is persisted on the parent session
- Successful escalation retries still pass through `VERIFYING`

## Prohibited patterns

1. `finalize_session(success=True)` outside `VerificationGateway`
2. Direct `SUCCEEDED` transitions outside the verified-success path
3. Child bridge sessions for internal escalation
4. Recursive `BridgeOrchestrator` construction in `session/services` or route executors
5. Unguarded prefix mutation (without `PolicyGate` + `prefix_lock`)
6. Treating route-level success as session-level success
7. Using prior-success lookup to bypass current verification
8. Inline success decisions in orchestrator execution paths

## Consequences

### Positive

- One coherent closed-loop system for `/bridge/run`
- Auditable verification provenance on every successful attempt
- Deterministic lifecycle transitions with optimistic concurrency
- Safer escalation and prefix mutation boundaries

### Negative

- More lifecycle transitions per attempt (latency overhead is small)
- All success paths must supply typed execution evidence
- Legacy fast paths (prefix profile skip) still require current verification

## Migration notes

- `PrefixReadinessProfile` remains a prefix readiness cache only; it is **not** a compatibility profile
- `get_prior_success()` informs planning and ranking; it does not authorize current success
- Future `CompatibilityProfile` reuse must bind to `VerificationBinding` and still re-verify on reuse
- Compliance/autopilot internals are not wrapped in this lifecycle; host-policy debt remains separate

## Related artifacts

- `alma_bridge/session/verification_gateway.py`
- `alma_bridge/session/services/verification.py`
- `tests/test_verification_authority.py`
- `tests/test_architecture_invariants.py`
- `docs/design/compatibility-profile-design.md`
