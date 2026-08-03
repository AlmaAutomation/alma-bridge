# ADR-022: Native Runtime Development Laboratory

## Status

Accepted — 2026-08-03

## Context

ACI Phases 1–4, Native Runtime Engineering Platform v1 ([ADR-020](ADR-020-native-runtime-engineering-platform.md)),
Runtime Certification Platform v1 ([ADR-021](ADR-021-runtime-certification-platform.md)), and Evidence v2.0
provide expansion candidates, engineering profiles, certification levels, and immutable evidence bundles.

Expansion candidates identify bounded runtime gaps (e.g. `append_existing_file` via
`file_append_unsupported.exe`), but there is no structured workflow for human engineers to scope,
track, and verify implementation work without conflating coordination with autonomous execution.

## Decision

Introduce **Alma Native Runtime Development Laboratory v1** under `alma_bridge/native_lab/`:

### 1. Engineering work items

`NativeRuntimeEngineeringWorkItem` records scoped human engineering work derived from expansion
candidates. Each item binds to provider, capability, behavior, bounded scope, demand, impact,
acceptance criteria, required fixtures/tests/benchmarks, and security review items.

### 2. Append-only lifecycle

Status transitions are append-only events. Completion requires configured evidence gates — source
code change alone is insufficient. The laboratory never marks work complete automatically.

### 3. Deterministic checklists and acceptance criteria

Eight checklist categories (Design, Implementation, Testing, Conformance, Performance,
Verification, Certification, Governance) with deterministic item generation per work item.
`EngineeringAcceptanceCriterion` tracks pending/satisfied/failed/waived states. Critical
security and verification criteria cannot be silently waived.

### 4. Dependency graph and risk review

DAG with cycle detection, blocked-by reporting, and critical-path planning metadata.
Structured security and semantic risk reviews with severity, likelihood, mitigation, and
residual risk.

### 5. Evidence attachments (read-only links)

Evidence references link to existing artifacts without mutating source evidence. If source
evidence changes, `evidence_stale=true` is set without rewriting historical attachments.

### 6. HTTP API and CLI

Read GET routes and human-workflow POST routes under `/bridge/native-lab/*`. POST mutations
alter only lab records — never execute binaries, write runtime source, change provider
selection, issue certifications, or alter VerificationEngine results.

CLI commands (`alma-native-lab`) provide list, show, create-from-candidate, checklist,
attach-test-evidence, and request-certification workflow coordination.

### 7. Evidence timeline integration

Lab lifecycle events append to the evidence timeline: `EngineeringWorkItemCreated`,
`EngineeringWorkItemAccepted`, `ImplementationEvidenceAttached`, `BehaviorTestsCompleted`,
`VerificationRequested`, `CertificationRequested`, `EngineeringWorkItemCompleted`,
`EngineeringWorkItemSuperseded`.

### 8. Explorer dashboard

Alma Explorer panel at `/native-lab` in almasysdet presents backlog, active work, dependency
graph, verification queue, certification queue, completed items, and history. Human workflow
actions only — no auto-implement, auto-certify, or runtime mutation.

## Consequences

- Human engineers retain implementation authority
- Expansion candidates become auditable, scoped engineering cards
- Completion is evidence-gated, not status-click gated
- Historical evidence and certification records remain immutable
- The laboratory coordinates; it does not implement Windows APIs

## References

- [native-runtime-development-laboratory.md](../architecture/native-runtime-development-laboratory.md)
- [native-runtime-engineering-workflow.md](../developer/native-runtime-engineering-workflow.md)
- [ADR-019](ADR-019-capability-guided-runtime-expansion.md)
- [ADR-020](ADR-020-native-runtime-engineering-platform.md)
- [ADR-021](ADR-021-runtime-certification-platform.md)
