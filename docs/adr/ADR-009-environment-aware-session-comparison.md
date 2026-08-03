# ADR-009: Environment-Aware Session Comparison

## Status

Accepted — 2026-07-28

## Context

Alma v1.1 Phase 1 attached deterministic run environment identity to sessions and
exposed an application catalog. Operators still need a direct, read-only way to
compare two specific sessions side-by-side and see which environment, strategy,
verification, framework, and runtime observations changed.

Regression intelligence compares aggregated knowledge profiles and may describe
`ENVIRONMENT_CHANGED` at the application level. Session comparison must remain
session-scoped, evidence-backed, and must not infer causality from correlation.

## Decision

1. Add a read-only `alma_bridge/comparison/` package with pure
   `SessionComparisonDiffEngine.compare(before, after)` over session snapshots.
2. Expose comparison via GET-only routes:
   - `/bridge/comparison/sessions/{baseline}/{comparison}`
   - `/bridge/comparison/applications/{fingerprint}?baseline=...&comparison=...`
3. Require matching application fingerprints; missing sessions return 404; malformed
   evidence returns 422.
4. Missing environment fields remain null/unknown — never fabricated.
5. When both environment and authoritative verification outcome change, include an
   explicit non-causality notice. Do not emit prescriptive remediation language.
6. Every changed field carries evidence references from baseline and/or comparison
   session artifacts.

## Consequences

- Operators can compare any two compatible sessions with provenance.
- Comparison reads do not ingest graph nodes, mutate prefixes, or invoke the planner.
- Legacy sessions without run environment data remain readable with null environment
  fields.

## References

- [ADR-005: Compatibility Regression Intelligence](./ADR-005-compatibility-regression-intelligence.md)
- [ADR-008: Compatibility Run Environment and Catalog](./ADR-008-compatibility-run-environment-catalog.md)
