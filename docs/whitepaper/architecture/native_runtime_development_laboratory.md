# Native Runtime Development Laboratory

The Native Runtime Development Laboratory coordinates human engineering work for
native_alma runtime gaps. It transforms evidence-backed expansion candidates into
structured, auditable engineering work items without implementing Windows APIs or
executing binaries from dashboards.

## Purpose

Expansion planning identifies bounded gaps (e.g. `append_existing_file` via
`file_append_unsupported.exe`). The laboratory provides the engineering card: scoped
work items with deterministic checklists, acceptance criteria, dependency graphs, risk
reviews, and evidence-gated completion.

## Workflow

```
Expansion Candidate → Engineering Work Item → Human Implementation
  → Test/Benchmark Evidence → Verification → Certification → Governance → Completed
```

Human engineers retain implementation authority. The laboratory coordinates; it does
not generate code, mutate runtime source, or auto-promote capabilities.

## Engineering work items

Each `NativeRuntimeEngineeringWorkItem` binds to:

- Provider, capability, and behavior identifiers
- Bounded implementation scope
- Source expansion candidate
- Observed demand and bounded impact estimates
- Acceptance criteria and required fixtures/tests/benchmarks
- Security review items
- Append-only status history

## Evidence gates

Completion requires configured evidence gates — not source code change alone. Critical
security and verification acceptance criteria cannot be silently waived. Evidence
attachments are read-only links; if source evidence changes, attachments are marked
`evidence_stale` without rewriting history.

## Boundaries

The laboratory must not execute binaries from GET endpoints, alter provider selection,
issue certifications automatically, or mutate historical evidence.

## Explorer integration

Alma Explorer at `/native-lab` presents backlog, active work, dependency graphs,
verification and certification queues, and history. Human workflow actions only — no
auto-implement or auto-certify.

See [ADR-022](../../adr/ADR-022-native-runtime-development-laboratory.md) and
[native-runtime-development-laboratory.md](../../architecture/native-runtime-development-laboratory.md).
