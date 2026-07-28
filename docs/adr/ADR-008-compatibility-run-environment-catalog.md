# ADR-008: Compatibility Run Environment and Application Catalog

## Status

Accepted

## Context

Alma Bridge v1.1 Phase 1 requires deterministic environment identity attached to
execution sessions and a read-only application catalog. Intelligence layers must
remain read-only with respect to execution.

## Decision

1. Persist `CompatibilityRunEnvironment` as immutable JSON on `bridge_sessions`
   (`run_environment_json`), captured once on the first persisted attempt via
   `BridgeOrchestrator._capture_session_run_environment`.
2. Surface environment evidence through `EvidenceBundleBuilder` as
   `run_environment:{session_id}` artifacts with `EvidenceSourceType.RUN_ENVIRONMENT`.
3. Extend graph (`environment` node, `session_used_environment` edge), knowledge
   (`observed_environments`), and regression (`ENVIRONMENT_CHANGED`) using the
   same provenance-backed patterns as v0.7–v1.0.
4. Expose `GET /bridge/catalog/applications` as a read-only aggregate over
   knowledge and regression evidence.

## Consequences

- Legacy sessions without environment data remain readable; missing fields are
  never fabricated.
- Read paths do not import orchestrator, remediation, or execution write APIs.
- Environment regression findings describe diffs only and avoid causality language.
