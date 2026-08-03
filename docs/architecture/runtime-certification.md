# Runtime Certification Platform

Alma continuously certifies NativeAlmaRuntime implementations through deterministic
evidence — proving exactly which behavioral semantics are implemented, unsupported,
verified, changed, and how confidence evolves.

## Pipeline

```
Implementation → Specification → Behavior tests → Benchmarks → Verification
    → Calibration → Governance → Certification → Historical evolution
```

## Core components

| Module | Role |
|--------|------|
| `models.py` | CertificationLevel, BehaviorCertification, ComplianceMatrix, CertificationRecord |
| `criteria.py` | Deterministic level computation from evidence |
| `behavioral_profiles.py` | Links native_engineering specs + ACI behavior profiles |
| `certificates.py` | Certificate generation from evidence |
| `compliance.py` | Compliance matrix builder |
| `verification_matrix.py` | API × behavior verification status |
| `versioning.py` | History, stale detection |
| `repository.py` | Append-only certification records |
| `queries.py` | Read-only aggregation |
| `service.py` | Orchestration |
| `dashboard.py` | Aggregated dashboard data |

## Certification levels

Scoped per `(capability_id, behavior_id)`:

1. **unverified** — no specification link
2. **specified** — deterministic spec from native_engineering
3. **behavior_tested** — behavior suite coverage (pass or documented-unsupported pass)
4. **verified** — validation results pass, fixture coverage complete
5. **calibrated** — calibration snapshot links present
6. **governed** — governance registry maturity observed (read-only)
7. **certified** — evidence bundles linked, no open regressions
8. **production_ready** — certified + benchmark history + 100% verification
9. **requires_revalidation** — stale; prior certification preserved with reason

## Behavior certification model

Each `BehaviorCertification` links (references, not duplication):

- Specification from `native_engineering`
- Expected semantics, supported/unsupported scenarios, known limitations
- Verification contracts, fixture coverage
- Calibration history (ACI `calibration_repository`, read-only)
- Governance history (governance registry, read-only)
- Benchmark history (`native_engineering` longitudinal)
- Research references
- Evidence bundle links, timeline references

## Compliance matrix

Deterministic matrix rows:

```
API × Behavior × Status × Coverage × Evidence count × Verification %
  × Regression status × Governance level
```

Example: `WriteFile / write_stdout / Certified / 100% / N bundles / 100% / None / Verified Bounded`

Unsupported behaviors show `Not Certified / Unsupported` with limitations.

## Stale detection

Certification becomes `requires_revalidation` when:

- Behavior regression (suite status fail)
- ABI change (spec_digest mismatch vs last record)
- Benchmark degradation
- Failed verification
- Provider implementation version change
- Governance registry version change

Certification history is append-only; stale items retain prior level in history.

## Integration (read-only)

| Source | Consumed data |
|--------|---------------|
| `native_engineering` | Specs, behavior suites, benchmarks |
| `compatibility_intelligence` | Calibration, governance, behavior_requirements |
| `evidence` | Bundles, timeline |
| `research` | Aggregate references |
| VerificationEngine | Outcomes (read-only) |

## HTTP API

All GET, read-only:

- `/bridge/certification/behaviors`
- `/bridge/certification/behaviors/{capability_id}/{behavior_id}`
- `/bridge/certification/matrix`
- `/bridge/certification/history/{capability_id}/{behavior_id}`
- `/bridge/certification/stale`
- `/bridge/certification/dashboard`

No POST apply. No binary execution on GET.

## Constraints

- No AI/LLM in certification decisions
- No auto-promote capabilities or certification levels
- No mutation of governance registry or certification history
- No inference of causation
- VerificationEngine authority unchanged
