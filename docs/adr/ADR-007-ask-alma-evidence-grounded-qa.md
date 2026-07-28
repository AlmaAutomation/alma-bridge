# ADR-007: Ask Alma is Evidence-Grounded and Read-Only

## Status

Accepted — 2026-07-28

## Context

Operators need to ask natural-language compatibility questions scoped to a
loaded application or session. Answers must come only from persisted Graph,
Knowledge, Regression, and Advisor evidence — not from general model knowledge
or execution systems.

## Decision

Introduce `alma_bridge/ask/` as a read-only Q&A layer:

```
User Question → QuestionClassifier → EvidenceQueryPlanner
  → read services → AskAlmaContext → DeterministicAnswerBuilder
  → OptionalLLMAnswerRenderer → policy validation → AskAlmaResponse
```

### 1. Read-only — no execution authority

Ask Alma never:

- Invokes planner or orchestrator
- Mutates prefixes, outcomes, or verification state
- Triggers graph ingestion on read paths
- Executes remediation or dependency installation
- Emits `ActionIntent`
- Recommends strategies or infers runtime requirements

`POST /bridge/ask` is allowed because it creates no persistent state and performs
no execution mutation.

### 2. Deterministic classification first

`QuestionClassifier` uses explicit pattern rules. Classification does not depend
on an LLM in Phase 1.

### 3. Minimal evidence fetches

`EvidenceQueryPlanner` maps question classes to the smallest necessary read
services (Knowledge, Regression, Advisor). Layers are not fetched blindly.

Graph ingestion is avoided on Ask paths; provenance comes from Knowledge and
Regression evidence references.

### 4. Provenance required

Every factual answer includes `evidence_references`. Insufficient evidence yields
an explicit limitation message.

### 5. Bounded optional LLM

Optional LLM rendering may rewrite wording only. It cannot add observations,
change verification semantics, or introduce recommendations. Validation failure
falls back to the deterministic answer with `render_mode=deterministic_fallback`.

### 6. Prohibited dependencies

The ask package must not import orchestrator, verification_gateway, session
mutations, winetricks, or ActionIntent.

## Consequences

- Positive: Scoped Q&A improves operator understanding without becoming an agent.
- Negative: Unsupported questions receive explicit limitation responses until
  classification expands in later phases.

## References

- ADR-004: Compatibility Knowledge aggregation
- ADR-005: Regression intelligence
- ADR-006: Advisor read-only boundary
