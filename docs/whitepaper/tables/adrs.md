# Architecture Decision Records

| ADR | Decision | Rationale | Status |
|-----|----------|-----------|--------|
| [ADR-001](../adr/ADR-001-authoritative-bridge-lifecycle.md) | `BridgeOrchestrator` is sole lifecycle owner; `VerificationGateway` is sole path to `SUCCEEDED` | Multiple subsystems previously inferred success from exit codes and proxy signals, producing false positives | Accepted — 2026-07-13 |
| [ADR-002](../adr/ADR-002-compatibility-intelligence-boundary.md) | Compatibility Intelligence is read-only; facts require evidence; verified success only from aggregate verification pass | Platform surfaces need deterministic assessment without re-entering execution authority | Accepted — 2026-07-27 |
| [ADR-003](../adr/ADR-003-compatibility-graph-non-authoritative.md) | Compatibility Graph is evidence-derived, non-authoritative; every edge requires provenance; `verified_by` only when verification passed | Operators need traversable compatibility relationships without planner/orchestrator coupling | Accepted — 2026-07-27 |
| [ADR-004](../adr/ADR-004-compatibility-knowledge-aggregation.md) | Knowledge aggregation is read-only, deterministic; conflicts preserved; success metrics use `aggregate_verification_passed` only | Cross-session summaries must not collapse competing framework evidence | Accepted — 2026-07-28 |
| [ADR-005](../adr/ADR-005-compatibility-regression-intelligence.md) | Regression compares baseline (excluding session X) vs current profiles via pure `RegressionDiffEngine` | Detect verified-outcome regressions and evidence shifts without execution or advisory inference | Accepted — 2026-07-28 |
| [ADR-006](../adr/ADR-006-ai-advisor-read-only-boundary.md) | Advisor is read-only and deterministic in Phase 1; forbidden prescriptive language; optional LLM render later | Explanations must cite provenance without strategy recommendations or execution control | Accepted — 2026-07-28 |
| [ADR-007](../adr/ADR-007-ask-alma-evidence-grounded-qa.md) | Ask Alma is evidence-grounded Q&A; deterministic classification first; optional LLM wording only | Scoped operator questions without becoming an execution agent | Accepted — 2026-07-28 |
| [ADR-008](../adr/ADR-008-compatibility-run-environment-catalog.md) | Persist `CompatibilityRunEnvironment` on sessions; expose catalog via GET; environment in graph/knowledge/regression | Deterministic environment identity for comparison and catalog surfaces | Accepted |
| [ADR-009](../adr/ADR-009-environment-aware-session-comparison.md) | Session comparison is read-only pair diff with explicit non-causality when environment and verification both change | Operators need session-scoped diffs distinct from application-level regression | Accepted — 2026-07-28 |

**Related design (not ADR):** Plugin architecture — design-only stub, Phase 8 (`docs/architecture/plugin-architecture.md`).
