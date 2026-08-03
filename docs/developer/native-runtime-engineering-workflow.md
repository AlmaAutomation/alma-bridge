# Native Runtime Engineering Workflow

## Overview

Human engineers use the Native Runtime Development Laboratory to coordinate scoped runtime
implementation work. The laboratory provides engineering cards, checklists, and evidence
tracking — not code generation or execution.

## Creating a Work Item

### From expansion candidate (CLI)

```bash
alma-native-lab create-from-candidate <candidate-id>
```

### From expansion candidate (API)

```http
POST /bridge/native-lab/work-items
Content-Type: application/json

{
  "source_expansion_candidate_id": "<candidate-id>",
  "title": "Optional override title"
}
```

## Inspecting Work Items

```bash
alma-native-lab list
alma-native-lab show wi_native_alma_filesystem_basic_io_append_existing_file_v1
alma-native-lab checklist wi_native_alma_filesystem_basic_io_append_existing_file_v1
```

## HTTP API

### Read (GET)

| Endpoint | Description |
|----------|-------------|
| `GET /bridge/native-lab/work-items` | List work items |
| `GET /bridge/native-lab/work-items/{id}` | Work item detail + engineering card |
| `GET /bridge/native-lab/work-items/{id}/history` | Append-only status history |
| `GET /bridge/native-lab/work-items/{id}/checklist` | Deterministic checklist |
| `GET /bridge/native-lab/work-items/{id}/dependencies` | Dependency graph |
| `GET /bridge/native-lab/work-items/{id}/evidence` | Attached evidence links |
| `GET /bridge/native-lab/dashboard` | Workflow metrics |

### Human workflow (POST)

| Endpoint | Description |
|----------|-------------|
| `POST /bridge/native-lab/work-items` | Create from candidate |
| `POST /bridge/native-lab/work-items/{id}/status` | Transition status |
| `POST /bridge/native-lab/work-items/{id}/evidence` | Attach evidence reference |
| `POST /bridge/native-lab/work-items/{id}/risk-reviews` | Submit risk review |
| `POST /bridge/native-lab/work-items/{id}/acceptance` | Update acceptance criterion |
| `POST /bridge/native-lab/work-items/{id}/supersede` | Supersede with successor |

POST endpoints require API key when configured (see governance routes pattern).

## Attaching Evidence

```bash
alma-native-lab attach-test-evidence <work-item-id> <artifact-path-or-id>
```

Evidence attachments are read-only links. Source evidence is never mutated.

## Requesting Certification

```bash
alma-native-lab request-certification <work-item-id>
```

This transitions the work item toward `certification_pending` and records a timeline event.
It does **not** issue a certification.

## Checklist Categories

1. **Design** — semantics, access modes, error modes, workspace boundaries
2. **Implementation** — human implementation milestones (tracked, not executed)
3. **Testing** — behavior suites and fixture verification
4. **Conformance** — API profile validation
5. **Performance** — benchmark evidence
6. **Verification** — VerificationEngine review request
7. **Certification** — certification review request
8. **Governance** — registry and scope preservation

## Completion Criteria

A work item reaches `completed` only when:

- All configured evidence gates are satisfied
- Critical acceptance criteria are satisfied or explicitly waived with reviewer
- Required checklist items in Verification, Certification, and Governance are evaluated
