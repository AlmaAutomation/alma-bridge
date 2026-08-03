# Native Runtime Development Laboratory

## Purpose

The Native Runtime Development Laboratory coordinates human engineering work for native_alma
runtime gaps. It transforms expansion candidates into structured, auditable engineering work
items without implementing Windows APIs, executing binaries from dashboards, or auto-promoting
capabilities.

## Workflow

```
Expansion Candidate
    → Engineering Work Item (scoped card)
    → Human Implementation (outside laboratory)
    → Test/Benchmark Evidence (attached as read-only links)
    → Verification Request
    → Certification Request
    → Governance Review
    → Completed (evidence-gated)
```

## Core Components

| Module | Responsibility |
|--------|----------------|
| `models.py` | Work items, acceptance criteria, status events |
| `candidates.py` | Create work items from expansion candidates |
| `checklists.py` | Deterministic checklist generation (8 categories) |
| `acceptance.py` | Acceptance criteria management and waivers |
| `dependencies.py` | DAG with cycle detection |
| `risk_review.py` | Security and semantic risk reviews |
| `evidence_links.py` | Read-only evidence attachments |
| `status.py` | Append-only status transitions |
| `repository.py` | Append-only persistence |
| `service.py` | Orchestration |

## Status States

`proposed` → `triaged` → `accepted` → `in_design` → `implementation_in_progress` →
`implementation_complete` → `testing` → `verification_pending` → `certification_pending` →
`governance_pending` → `completed`

Terminal/alternate: `blocked`, `rejected`, `superseded`

## Evidence Gates

Completion requires:

- Required acceptance criteria satisfied (critical items not silently waived)
- Behavior test evidence attached when testing phase reached
- Verification evidence when verification requested
- Security review items addressed

## Boundaries

The laboratory **must not**:

- Generate implementations or modify NativeAlmaRuntime source
- Execute binaries from GET or dashboard endpoints
- Alter provider selection or registry
- Promote capabilities or issue certifications automatically
- Mutate historical evidence

## Seeded Work Item

`wi_native_alma_filesystem_basic_io_append_existing_file_v1` scopes PE64 console synchronous
workspace-confined append for `filesystem.basic_io` / `append_existing_file`, sourced from
`file_append_unsupported.exe` expansion candidate evidence.

## API

See [native-runtime-engineering-workflow.md](../developer/native-runtime-engineering-workflow.md)
for endpoint and CLI reference.
