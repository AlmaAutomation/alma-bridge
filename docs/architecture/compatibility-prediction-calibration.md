# Compatibility Prediction Calibration

ACI Phase 2 compares **statically predicted** compatibility with
**authoritatively verified** execution outcomes to build deterministic
calibration evidence.

## Architecture flow

```
Static PE analysis
       ↓
ACI prediction (+ behavior coverage)
       ↓
PredictionSnapshot (immutable, versioned)
       ↓
Normal Bridge execution
       ↓
VerificationEngine (sole success authority)
       ↓
OutcomeLink (session + verification binding)
       ↓
CalibrationRecord (classification + attribution)
       ↓
CalibrationMetrics (rates with sample sizes)
```

## Prediction snapshot

Persisted **before** execution. Fields:

| Field | Purpose |
|-------|---------|
| `snapshot_id` | Unique identifier |
| `analysis_digest` | Links to PE analysis artifact |
| `binary_digest` | SHA-256 of exact PE bytes |
| `provider_id`, `provider_version` | Provider capability snapshot |
| `capability_registry_version` | Registry version at prediction time |
| `api_registry_version` | API registry version at prediction time |
| `required_capabilities` | Capabilities inferred from imports |
| `unsupported_capabilities` | Declared unsupported for provider |
| `unknown_apis` | Unclassified imports |
| `delegated_capabilities` | Delegated to another provider |
| `static_coverage` | Symbol/capability coverage breakdown |
| `behavior_coverage` | Behavioral profile coverage (Phase 2) |
| `confidence_level`, `confidence_score` | Deterministic confidence |
| `blockers` | Pre-execution blockers |
| `prediction` | Full `CompatibilityPrediction` payload |
| `created_at`, `schema_version`, `engine_version` | Provenance |

Snapshots are immutable. Historical calibration always uses the registry
versions stored in the snapshot — never recomputes with current registries.

## Outcome linking

Links snapshots to completed Bridge sessions:

| Field | Purpose |
|-------|---------|
| `outcome_id` | Unique identifier |
| `snapshot_id` | Prediction being evaluated |
| `session_id`, `attempt_id` | Bridge session binding |
| `binary_digest` | Must match snapshot |
| `provider_id`, `provider_version` | Runtime provider used |
| `outcome_type` | Authoritative outcome category |
| `verification_result_ref` | VerificationEngine result reference |
| `predicted_eligible` | Whether snapshot predicted eligibility |
| `verified_success` | Whether VerificationEngine confirmed success |

Binding rules:

- Application A's outcomes cannot calibrate application B (digest mismatch)
- Provider A's outcomes cannot calibrate provider B (provider mismatch)
- Missing binding evidence → `indeterminate`

## Calibration classifications

| Classification | Predicted | Verified |
|----------------|-----------|----------|
| `true_positive` | eligible | success |
| `false_positive` | eligible | failure |
| `true_negative` | ineligible | missing requirement confirmed |
| `false_negative` | ineligible | success |
| `indeterminate` | any | no authoritative outcome |

## Failure attribution

For `false_positive` records only. Requires evidence from verification result,
failure signature, or behavioral profile gap. Never guesses — returns `unknown`
when evidence is insufficient.

## Confidence calibration

Deterministic adjustments to pre-execution confidence using:

- Prior verified history for matching capability set
- Behavior coverage vs symbol coverage delta
- Unknown API count and dynamic import indicators
- TLS/delay import flags
- Provider maturity
- Prior false-positive rate for matching capability set
- Registry freshness

All factors are logged in `confidence.factors` for explainability.

## Integration points

1. **Before plan** — `BridgeOrchestrator._create_aci_prediction_snapshot`
   mirrors `_create_shadow_prediction_before_plan`
2. **After finalize** — `BridgeOrchestrator._record_aci_calibration_outcome`
   mirrors `_record_shadow_actual_outcome`

Neither hook bypasses VerificationEngine or mutates provider registries.

## Terminology

| Term | Meaning |
|------|---------|
| statically predicted | Pre-execution ACI assessment from PE analysis |
| behaviorally covered | Required API behavior profile supported by provider |
| authoritatively verified | VerificationEngine declared outcome |
| prediction confirmed | true_positive or true_negative |
| prediction contradicted | false_positive or false_negative |

Never use "compatible" without a predicted vs verified qualifier.
