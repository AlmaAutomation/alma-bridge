# Engineering Certification

Alma continuously certifies runtime implementations against deterministic behavioral
specifications — evolving from "We implemented WriteFile" to "We can prove exactly
which WriteFile semantics are implemented, unsupported, verified, changed, and how
confidence evolves."

## Purpose

The Runtime Certification Platform closes the loop between implementation,
specification, behavior testing, verification, calibration, and governance. Every
certification decision is explainable with evidence references; certification never
depends on symbol export alone.

## Certification model

Certification is **behavior-scoped**, not subsystem-scoped. Each
`(capability_id, behavior_id)` pair receives a level computed deterministically from:

- Native engineering specifications and behavior suites
- ACI behavior profiles and verified scenarios
- Calibration snapshots (read-only)
- Governance registry maturity (read-only, never auto-promoted)
- Evidence bundles and timeline entries
- Benchmark longitudinal history

## Level progression

```
unverified → specified → behavior_tested → verified → calibrated
  → governed → certified → production_ready
```

When evidence degrades or upstream artifacts change, the level becomes
`requires_revalidation`. Prior certification history is preserved append-only.

## Compliance matrix

Operators view an API × behavior matrix showing status, coverage percentage, evidence
count, verification percentage, regression status, and governance level. Unsupported
behaviors (e.g. `append_existing_file`, `overlapped_io`) appear as **Not Certified /
Unsupported** with documented limitations — reflecting behavioral gaps, not missing
symbols.

## Historical evolution

Certification records append over time:

```
August: Specified → September: Behavior Tested → October: Verified → November: Certified
```

Each transition carries evidence references explaining why the level changed.

## Relationship to verification authority

Certification **observes** VerificationEngine outcomes; it does not replace or
override verification authority. Runtime selection and execution gates remain
unchanged.

## Explorer integration

The Alma Explorer `/certification` dashboard surfaces certified APIs, compliance
matrix, stale items, benchmark history, and evidence links — all read-only.
