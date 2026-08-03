# Read-Only Intelligence — Architecture Deep-Dive

**Status:** As-built with executable boundary tests  
**Companion:** [dependency_boundaries.mmd](../diagrams/dependency_boundaries.mmd)

## Invariant

The platform tier (intelligence, graph, knowledge, regression, comparison, advisor, ask, catalog) **must never** import or invoke execution authority: orchestrator, verification gateway, prefix mutations, winetricks, or `ActionIntent`.

Phase 1 audit verdict: **no critical violations** (`READ_ONLY_BOUNDARIES.md` §2, `ARCHITECTURE_REPORT` §5).

## Forbidden import fragments (enforced in tests)

```
"orchestrator", "verification_gateway", "session.mutations", "winetricks", "ActionIntent"
```

Each read-only package includes `tests/*/test_*architecture_boundaries.py` asserting:

1. No forbidden fragments in package source
2. Route modules are GET-only (except Ask — POST without writes)
3. Importing routes does not load orchestrator into `sys.modules`
4. Sample GET does not trigger graph ingestion / `record_attempt` (advisor test)

## Package dependency order

```
intelligence (evidence)
    → graph
    → knowledge (also direct from intelligence)
    → regression
    → comparison (also uses knowledge types)
    → advisor
    → ask
catalog ← intelligence + knowledge + regression (parallel browser)
```

All packages depend on `intelligence.EvidenceBundleBuilder` directly or transitively.

## Documented smells (not violations)

### Pure predicate import

`knowledge/aggregation.py` and `comparison/queries.py`:

```python
from alma_bridge.session.stop_on_success_verification import aggregate_verification_passed
```

Pure function; no I/O. Recommended relocation to neutral module (Phase 3 work plan).

### Private cross-package calls

- `intelligence/repository.py` → `outcomes._connect()`
- `comparison/queries.py` → `KnowledgeAggregationEngine._to_knowledge_ref()`

## HTTP surface rules

| Layer | Methods | Mutations |
|-------|---------|-----------|
| Intelligence, Graph, Knowledge, Regression, Comparison, Advisor, Catalog | GET | None |
| Ask Alma | POST | None (question body only) |
| Graph GET | GET | Idempotent ingestion writes graph tables only — not execution |

## Advisor and Ask LLM boundaries

Optional LLM renderers (`advisor/llm/`, `ask/answer.py`) may rewrite wording when `settings.advisor_llm_enabled`. Policy validation forbids prescriptive phrases (ADR-006). LLM cannot add facts or change verification semantics (ADR-007 §5).

## Observation vs execution separation

| Observation (platform) | Execution (core) |
|------------------------|-------------------|
| Read `verification_json` structurally | Invoke `VerificationEngine` |
| Count verified success via predicate | Declare `SUCCEEDED` |
| Explain regression diff | Retry with remediation |
| Compare session environments | Capture `run_environment_json` on first attempt |

## Hardening recommendations (Future work — Phase 3)

From `READ_ONLY_BOUNDARIES.md` §5:

1. Centralize forbidden fragment list in `tests/_boundaries.py`
2. Meta-test covering all read-only packages
3. Relocate verification predicate
4. Public read APIs on storage and knowledge mapper

## Related documents

- [READ_ONLY_BOUNDARIES.md](../../architecture/READ_ONLY_BOUNDARIES.md)
- [API_BOUNDARIES.md](../../architecture/API_BOUNDARIES.md) §2
- ADRs 002–007, 009
