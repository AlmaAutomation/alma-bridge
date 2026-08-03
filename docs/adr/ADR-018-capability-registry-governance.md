# ADR-018: Capability Registry Governance and Evidence-Based Promotion

## Status

Accepted — 2026-08-02

## Context

ACI Phase 1 provides static PE analysis and capability coverage prediction.
ACI Phase 2 adds prediction snapshots, outcome linking, and calibration metrics
([ADR-017](ADR-017-compatibility-prediction-calibration.md)). Calibration
evidence measures prediction accuracy but must **not** automatically mutate
provider capability registries or provider-selection logic.

Operators need a deterministic, auditable process to promote or demote
provider capability maturity using calibration evidence — with human approval
for every registry state change.

## Decision

Introduce **Capability Registry Governance** under
`alma_bridge/compatibility_intelligence/governance/`:

### 1. Capability maturity states

Scoped maturity states (never global from a single fixture):

| State | Meaning |
|-------|---------|
| `declared` | Capability listed; no behavioral evidence |
| `experimental` | Initial implementation; limited scope |
| `behaviorally_tested` | Required behavior scenarios executed; evidence resolves |
| `calibration_supported` | Prediction snapshots linked; minimum resolved sample count |
| `verified_bounded` | Repeated authoritative success within bounded scope |
| `stable` | Broader coverage, security review, regression suite stable |
| `deprecated` | Scheduled for removal; reduced eligibility |
| `revoked` | No longer eligible; explicit registry version required |

Scope dimensions: `provider_id`, `provider_version`, `capability_id`,
`behavior_profile`, `architecture`, `application/fixture scope`,
`implementation_version`.

### 2. Promotion proposals (evidence-derived, not auto-applied)

Proposals are created from calibration records and behavior profiles. Fields
include current/proposed state, scope, supporting calibration record IDs,
verified success/failure counts, false-positive/negative counts, behavior
scenarios, evidence references, limitations, registry version, and
deterministic proposal digest.

Creating a proposal does **not** change the registry.

### 3. Deterministic promotion policy

Policy rules in `policy.py` gate each transition:

- `experimental` → `behaviorally_tested`: required behavior scenarios
  executed; all evidence resolves; no hidden unsupported behavior
- `behaviorally_tested` → `calibration_supported`: linked prediction
  snapshots; minimum resolved sample count; no unexplained false positives
  above threshold
- `calibration_supported` → `verified_bounded`: repeated authoritative success
  within bounded scope; required behavior coverage complete; zero unresolved
  blocking gaps
- `verified_bounded` → `stable`: broader scenario coverage; version
  compatibility; security review; regression suite stable; explicit human
  approval

Never infer general stability from aggregate success rate alone.

### 4. Human review (digest-bound)

Review states: `approved`, `rejected`, `needs_revision`. Approval binds to
the exact proposal digest at review time.

### 5. Append-only versioned registry

- Every registry change creates a **new** version; previous versions remain
  readable and immutable
- Rollback creates a new version (no in-place historical mutation)
- Prediction snapshots bind to the registry version active at prediction time
- Apply updates **only** the versioned capability registry — no execution,
  prefix mutation, or session outcome changes

### 6. API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/bridge/compatibility/governance/proposals` | List proposals |
| GET | `/bridge/compatibility/governance/proposals/{id}` | Get proposal |
| POST | `/bridge/compatibility/governance/proposals` | Create from evidence |
| POST | `/bridge/compatibility/governance/proposals/{id}/reviews` | Human review |
| POST | `/bridge/compatibility/governance/proposals/{id}/apply` | Apply approved proposal |

### 7. Hard constraints

- No automatic capability promotion
- No automatic provider-selection changes
- No execution from governance endpoints
- No ML
- VerificationEngine remains sole outcome authority
- Human approval required for every registry state change
- Calibration failure cannot mutate registry

## Consequences

- Explorer gains a Capability Governance panel showing scope-aware maturity,
  calibration sample sizes, and review history
- `console.stdout` for `native_alma` may reach `verified_bounded` for
  hello/stdout fixtures via the proposal workflow
- `filesystem.basic_io` retains `append_existing_file` limitations regardless
  of other promotions
- Tests enforce boundary matrix (18 scenarios) including cross-scope and
  cross-provider isolation

## References

- [ADR-002](ADR-002-compatibility-intelligence-boundary.md)
- [ADR-017](ADR-017-compatibility-prediction-calibration.md)
