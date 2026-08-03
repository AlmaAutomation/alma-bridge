# ADR-017: Compatibility Prediction Calibration

## Status

Accepted — 2026-08-02

## Context

ACI Phase 1 (`compatibility_intelligence/`) produces **statically predicted**
compatibility assessments from read-only PE analysis: required capabilities,
provider symbol coverage, and deterministic confidence. These predictions are
useful for planning but are not authoritative — only `VerificationEngine` may
declare verified success ([ADR-001](ADR-001-authoritative-bridge-lifecycle.md),
[ADR-002](ADR-002-compatibility-intelligence-boundary.md)).

Phase 2 closes the loop: compare pre-execution predictions with post-execution
verification outcomes to measure prediction accuracy, expose behavioral gaps, and
calibrate confidence — without mutating provider registries or bypassing
verification authority.

## Decision

Introduce **Prediction Calibration** as a deterministic, read-only evidence
layer under `alma_bridge/compatibility_intelligence/`:

### 1. Immutable prediction snapshots

Before Bridge execution, persist an immutable `PredictionSnapshot` bound to:

- `binary_digest` — exact PE bytes analyzed
- `analysis_digest` — analysis artifact identity
- `provider_id` + `provider_version` — capability snapshot at prediction time
- `capability_registry_version` + `api_registry_version` — registry versions used
- Full prediction payload: required/unsupported/unknown capabilities, static
  coverage, confidence, blockers

Snapshots are never recomputed with newer registries when evaluating historical
accuracy.

### 2. Outcome linking via VerificationEngine

After `VerificationGateway` completes, link snapshots to authoritative outcomes
using session ID, attempt ID, and verification result reference. Outcome types:

| Type | Meaning |
|------|---------|
| `verified_success` | VerificationEngine declared success |
| `verified_failure` | VerificationEngine declared failure |
| `unverifiable` | No authoritative verification |
| `execution_not_attempted` | Session blocked before execution |
| `provider_ineligible` | Provider could not run binary |
| `blocked_by_policy` | Policy prevented execution |
| `runtime_fault` | Runtime error before verification |
| `verification_inconclusive` | Verification ran but inconclusive |

`unverifiable` outcomes are **never** counted as success or failure in calibration
rates.

### 3. Calibration classifications

| Classification | Condition |
|----------------|-----------|
| `true_positive` | Predicted eligible + verified success |
| `false_positive` | Predicted eligible + verified failure |
| `true_negative` | Predicted ineligible + evidence confirms missing requirement |
| `false_negative` | Predicted ineligible + verified success |
| `indeterminate` | No authoritative outcome or insufficient binding evidence |

### 4. Behavioral capability profiles

Distinguish **symbol coverage** (import present + API classified) from
**behavior coverage** (requested API semantics supported). A binary may have
100% symbol coverage while a specific behavior (e.g., append-to-existing file)
is unsupported. Static symbol coverage must never be relabeled as verified
compatibility.

### 5. Failure attribution (false positives only)

When a false positive occurs, attribute the gap with evidence:

`unsupported_dynamic_import`, `capability_declared_too_broadly`,
`API_semantics_incomplete`, `unsupported_API_flag_or_mode`,
`process_environment_gap`, `loader_gap`, `ABI_gap`,
`filesystem_semantics_gap`, `synchronization_gap`, `exception_handling_gap`,
`resource_or_manifest_gap`, `verification_contract_mismatch`,
`non_runtime_application_failure`, `unknown`

Attribution remains `unknown` when evidence is insufficient.

### 6. Hard constraints (non-negotiable)

- VerificationEngine remains the **only** success authority
- Static coverage is never relabeled as verified compatibility
- No ML; all scoring remains deterministic and explainable
- Do not auto-add unknown APIs to capabilities
- Do not silently change provider support declarations
- Do not execute binaries from GET/read endpoints
- Do not auto-prefer NativeAlmaRuntime based solely on coverage
- Calibration does not trigger automatic remediation

### 7. API surface (read-only GET)

- `GET /bridge/compatibility/calibration`
- `GET /bridge/compatibility/calibration/capabilities/{capability_id}`
- `GET /bridge/compatibility/calibration/analyses/{analysis_digest}`

Metrics expose sample sizes (numerator/denominator). No execution on GET.

## Consequences

- Operators can see what Alma predicted, why, what verification established,
  and whether the prediction was confirmed or contradicted.
- Behavioral fixtures prove ACI reasons beyond import names.
- Confidence scoring incorporates prior false-positive rates without ML.
- Explorer UI preserves the distinction between statically predicted and
  authoritatively verified compatibility.

## References

- [compatibility-prediction-calibration.md](../architecture/compatibility-prediction-calibration.md)
- [capability-behavior-profiles.md](../architecture/capability-behavior-profiles.md)
- [aci-calibration-fixtures.md](../testing/aci-calibration-fixtures.md)
- ADR-002, ADR-016
