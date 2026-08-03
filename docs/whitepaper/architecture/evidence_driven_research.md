# Evidence-Driven Compatibility Research

**Status:** Implemented (Alma Research Platform v1)  
**Package:** `alma_bridge/research/`  
**API prefix:** `GET /bridge/research/*`

## Purpose

Alma Research Platform transforms accumulated compatibility evidence into **deterministic engineering knowledge**. It answers questions such as:

- Which Windows capabilities most commonly block compatibility?
- Which runtime behaviors most often appear in false-positive calibration records?
- Which engineering investments would produce the greatest verified compatibility gain?
- How has NativeAlmaRuntime improved over time?
- Which behavior profiles remain the largest unknowns?

Research is **read-only**: no execution, no registry mutation, no AI inference, no causation claims.

## Architecture

```
CompatibilityEvidenceBundle ──┐
Prediction snapshots        ──┤
Calibration records         ──┼──► ResearchQueries ──► Analytics / Trends / Evolution
Governance proposals        ──┤         │
Expansion plans             ──┤         ▼
Timeline events             ──┘   ReportGenerator ──► ResearchReport (deterministic digest)
Capability registry (RO)          │
                                    ▼
                              GET /bridge/research/*
```

## Report types

| Report type | Question answered |
|-------------|-------------------|
| `top_unsupported_behaviors` | Most frequently observed unsupported behaviors |
| `top_calibration_gaps` | Calibration gaps and false-positive associations |
| `most_observed_unknown_apis` | Unknown API imports ranked by frequency |
| `capability_maturity_growth` | Registry maturity evolution over time |
| `prediction_accuracy_over_time` | Calibration accuracy by time bucket |
| `behavior_coverage_evolution` | Behavior profile coverage snapshots |
| `native_runtime_growth` | NativeAlmaRuntime capability growth |
| `governance_velocity` | Governance proposal rate over time |
| `expansion_backlog` | Expansion plan candidate backlog |
| `verification_trends` | Verification success rate from timeline events |

## Required report metadata

Every report includes:

- `sample_size` (numerator/denominator)
- `time_window`
- `registry_version`
- `provider_versions`
- `confidence` (deterministic, explainable factors)
- `limitations`
- `evidence_references`
- `report_digest` (same inputs → same digest)

## Confidence model

Confidence is computed deterministically from sample coverage:

```
score = min(1.0, numerator / max(threshold, 1))
```

Factors document whether the sample meets minimum thresholds and whether coverage is partial. No statistical inference or ML.

## Language constraints

Report summaries are validated to exclude causation language (`causes`, `leads to`, etc.). Correlations are labeled **observed correlation — not causal**.

## Boundaries (MUST NOT)

- Change runtime selection or execution authority
- Mutate capability registry or evidence history
- Execute binaries on GET endpoints
- Generate AI conclusions
- Infer causation from co-occurrence statistics

## Integration points

| Source | Consumed via |
|--------|--------------|
| Evidence bundles | `EvidenceRepository`, `EvidenceQueries` |
| Calibration | `CalibrationService`, `CalibrationRepository` |
| Governance | `GovernanceRepository` |
| Expansion | `ExpansionPlanRepository` |
| Analyses | `AnalysisRepository` |
| Platform health | `EvidenceService.platform_health()` metrics patterns |

## Explorer

The almasysdet **Research Dashboard** (`/research`) consumes `GET /bridge/research/dashboard` and individual report endpoints. All metrics display sample sizes and limitations.

## Related documents

- [evidence_model.md](./evidence_model.md) — canonical evidence vocabulary
- [read_only_intelligence.md](./read_only_intelligence.md) — platform tier boundaries
- [compatibility_operating_system.md](./compatibility_operating_system.md) — Alma v2.0 lifecycle
