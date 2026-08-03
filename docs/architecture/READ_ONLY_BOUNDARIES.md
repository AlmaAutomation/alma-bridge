# Alma Bridge — Read-Only Boundaries

**Status:** Phase 1 Architecture Audit (documentation only)
**Companion:** [API_BOUNDARIES](./API_BOUNDARIES.md) · [DEPENDENCY_GRAPH](./DEPENDENCY_GRAPH.md)

This is the audit's verdict on the central invariant: **the platform tier (Advisor, Ask, Knowledge, Regression, Comparison, Graph, Intelligence, Catalog) must never import or invoke the execution authority** (Planner-as-orchestrator, Orchestrator, Execution, ActionIntent, Remediation, prefix mutations).

---

## 1. The forbidden set

The brief lists the forbidden modules as: **Planner, Orchestrator, Execution, ActionIntent, Remediation.**

The codebase enforces an equivalent set of *import fragments* in every read-only package's boundary test (`FORBIDDEN_IMPORT_FRAGMENTS`):

```
"orchestrator", "verification_gateway", "session.mutations", "winetricks", "ActionIntent"
```

Mapping brief → enforcement:

| Brief term | Enforced as | Notes |
|------------|-------------|-------|
| Orchestrator | `orchestrator` fragment + `sys.modules` load check | `learning.orchestrator` |
| Execution / prefix mutation | `session.mutations`, `winetricks` | prefix write + runtime install path |
| ActionIntent | `ActionIntent` (also full source scan in advisor) | plan-emission type |
| (verification authority) | `verification_gateway` | sole `SUCCEEDED` transition |
| Remediation | *not* a named fragment | covered indirectly — read-only pkgs import none of `execution`, `operator`, `automation` (verified by AST scan) |
| Planner | *not* a named fragment | `session.services.planner` is not imported by any read-only pkg (verified by AST scan) |

**Gap:** "Planner" and "Remediation" are not literal forbidden fragments in the tests. They are currently *not* imported (confirmed by this audit's full AST scan), but the guard would not catch a future regression that imports `session.services.planner` or a `remediation` module. Recommendation: add `planner`, `remediation`, and `execution.` to `FORBIDDEN_IMPORT_FRAGMENTS` and centralize the list (see below).

---

## 2. Audit result per package

Full static AST scan of each package's imports (top-level + relative):

| Package | Imports orchestrator? | verification_gateway? | session.mutations? | execution/automation/operator? | ActionIntent? | Verdict |
|---------|:--:|:--:|:--:|:--:|:--:|---------|
| `intelligence` | no | no | no | no | no | ✅ clean |
| `graph` | no | no | no | no | no | ✅ clean |
| `knowledge` | no | no | no | **session (pred only)** | no | ⚠️ smell |
| `regression` | no | no | no | no | no | ✅ clean |
| `comparison` | no | no | no | **session (pred only)** | no | ⚠️ smell |
| `advisor` (+`llm`) | no | no | no | no | no | ✅ clean |
| `ask` | no | no | no | no | no | ✅ clean |
| `catalog` | no | no | no | no | no | ✅ clean |

**No critical boundary violations were found.** No read-only package imports the orchestrator, verification gateway, prefix mutations, execution, automation, operator, or emits `ActionIntent`.

---

## 3. The two documented smells (not violations)

Both `knowledge/aggregation.py:24` and `comparison/queries.py:15` contain:

```python
from alma_bridge.session.stop_on_success_verification import aggregate_verification_passed
```

Why this is only a **smell**, not a violation:
- `aggregate_verification_passed()` is a pure predicate over a mapping (`session/stop_on_success_verification.py`, lines 10–15). It performs no I/O, spawns no process, touches no orchestrator, gateway, or mutation.
- It exists so the read-path uses the **same** authoritative "did verification pass?" rule as the write-path — which is architecturally desirable (single source of truth).

Why it is still worth fixing:
- It creates a source-level dependency from the read-only tier onto the **core** `session` package, whose other modules (`mutations`, `verification_gateway`, `lifecycle`) are firmly off-limits. Importing *from* that package normalizes crossing the line.
- The current boundary tests only pass because the forbidden list happens not to include this module name.

**Recommendation (Phase 3):** relocate the verification-pass predicate(s) to a neutral, dependency-free module — e.g. `alma_bridge/schemas/verification_semantics.py` or `alma_bridge/evidence/verification.py` — imported by both `session` (write path) and the read-only tier (read path). Then no read-only package needs to import `session` at all.

---

## 4. Encapsulation caveats within the read-only tier

Even where the *core* boundary is clean, two internal-access patterns weaken read-only encapsulation:

1. `intelligence/repository.py` calls `outcomes._connect()` and `profile_store._connect` — private storage internals used for raw read SQL.
2. `comparison/queries.py` calls `KnowledgeAggregationEngine()._to_knowledge_ref(...)` — a private method of another read-only package.

Neither breaks the execution boundary, but both should become public, documented read interfaces.

---

## 5. Hardening recommendations (all Phase 3, no runtime change)

1. **Centralize the forbidden list.** Every boundary test copies the same 5-tuple. Extract to a shared `tests/_boundaries.py` and expand it to include `execution.`, `learning.orchestrator`, `session.services.planner`, `remediation`, `automation`, `operator`.
2. **Add a meta-test** that asserts *all* of `graph/knowledge/regression/comparison/advisor/ask/catalog/intelligence` are covered by the shared boundary check (so a new read-only package cannot ship without a boundary test).
3. **Relocate the verification predicate** out of `session` (removes the last read→core edge).
4. **Publicize** `_to_knowledge_ref` and add a public read API on `storage.outcomes` (`connect_readonly()` or query helpers) so `# noqa: SLF001` disappears.
4. **Keep Ask's POST documented** as read-only (it takes a body, writes nothing).
