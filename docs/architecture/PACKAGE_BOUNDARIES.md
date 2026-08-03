# Alma Bridge — Package Boundaries

**Status:** Phase 1 Architecture Audit (documentation only)
**Companion:** [DEPENDENCY_GRAPH](./DEPENDENCY_GRAPH.md) · [READ_ONLY_BOUNDARIES](./READ_ONLY_BOUNDARIES.md)

This document states, per package, the intended responsibility, allowed dependencies, and the observed boundary condition (clean / smell / violation).

---

## 1. Boundary contract per package

| Package | Responsibility | Allowed to import | Must NOT import | Observed |
|---------|----------------|-------------------|-----------------|----------|
| `schemas` | Domain + API pydantic models | stdlib, pydantic | any alma_bridge business logic | Clean |
| `config` | Settings / flags | pydantic-settings | anything | Clean |
| `storage` | `outcomes.db` CRUD, stats | config, compatibility(profile store init) | orchestrator, api | Clean* |
| `hardware` | Host profiling, prefixes, shims | config | api | Clean |
| `execution` | Process launch, preflight, privileges | bridge, compatibility, compliance, session, learning, storage, hardware, schemas, config | api | Core cycle member |
| `session` | Lifecycle, policy gate, mutations, verification | execution, bridge, compatibility, learning, automation, compliance, hardware, storage, schemas | api | Core cycle member |
| `learning` | Orchestrator, ranker, training | execution, session, bridge, compatibility, hardware, storage, schemas, config | api | Core cycle member |
| `compatibility` | Program kind, frameworks, profiles, shadow | execution, session, learning, hardware, validation, schemas, config | api | Core cycle member (36 modules) |
| `automation` | scan→assess→apply→verify spine | execution, compliance, learning, hardware, schemas, config, flagship | api | Core cycle member |
| `operator` | Autonomous loop | automation, compliance, execution, learning, session, hardware, storage, config | api | Core |
| `compliance` | TLS/DNS/drivers/modernization | automation, execution, hardware, config | api | Core cycle member |
| `importers` | Legacy dataset ingest | execution, learning, hardware, storage, config | api | Clean (ingest) |
| `validation` | Campaign guards, evidence | compatibility, execution, learning, schemas, storage, config | api | Core-adjacent |
| `intelligence` | **Evidence bundle builder** + assessment | compatibility, storage | orchestrator, gateway, mutations, execution | **Clean (read-only)** |
| `graph` | Compatibility graph nodes/edges | compatibility, intelligence, config | orchestrator, gateway, mutations, execution | **Clean (read-only)** |
| `knowledge` | Knowledge aggregation | compatibility, graph, intelligence, session(pred) | orchestrator, gateway, mutations, execution | **Read-only, 1 smell** |
| `regression` | Baseline vs current | compatibility, intelligence, knowledge | orchestrator, gateway, mutations, execution | **Clean (read-only)** |
| `comparison` | Environment-aware session diff | compatibility, graph, intelligence, knowledge, regression, session(pred) | orchestrator, gateway, mutations, execution | **Read-only, 1 smell** |
| `advisor` | Deterministic explanations (+LLM) | compatibility, graph, knowledge, regression, config | orchestrator, gateway, mutations, execution, ActionIntent | **Clean (read-only)** |
| `ask` | Evidence-grounded Q&A | advisor, knowledge, regression, config | orchestrator, gateway, mutations, execution | **Clean (read-only)** |
| `catalog` | App browser | intelligence, knowledge, regression, storage | orchestrator, gateway, mutations, execution | **Clean (read-only)** |
| `observability` | Prometheus metrics | learning, storage | api | Clean |
| `api` | HTTP routers + auth | everything | — (composition root) | Monolithic `routes.py` |
| `cli` | Shadow-validation CLI | compatibility, storage, validation | — | Clean |

\* `storage.outcomes` exposes a private `_connect()` that read-only adapters call across the package boundary (`# noqa: SLF001`). Functionally read-only, but it leaks an internal.

---

## 2. Encapsulation smells (private access across packages)

| Site | Access | Why it matters |
|------|--------|----------------|
| `intelligence/repository.py` `OutcomesStoreAdapter.list_sessions_for_fingerprint` | `outcomes._connect()` (private) | Read-only tier reaches into storage internals for raw SQL |
| `intelligence/repository.py` | `profile_store._connect` imported as `profile_connect` | Same, for profile DB |
| `comparison/queries.py:274` | `KnowledgeAggregationEngine()._to_knowledge_ref(...)` (`# noqa: SLF001`) | Comparison depends on a **private** method of the Knowledge engine — should be a public API |

These pass boundary tests (they are not forbidden fragments) but couple packages to each other's internals. Promote the used members to public interfaces (Phase 3).

---

## 3. Model / adapter duplication across boundaries

The read-only tier re-declares near-identical evidence-reference and error types per package instead of sharing one:

| Concept | Duplicated definitions |
|---------|------------------------|
| Evidence reference | `intelligence.models.EvidenceReference`, `knowledge.models.KnowledgeEvidenceReference` |
| "Not found" error | `IntelligenceNotFoundError`, `CatalogNotFoundError`, `ComparisonNotFoundError`, `AdvisorNotFoundError`, `AskAlmaNotFoundError`, `RegressionNotFoundError` |
| "Malformed evidence" error | `MalformedEvidenceError`, `MalformedKnowledgeEvidenceError`, `MalformedComparisonEvidenceError`, `MalformedAdvisorError` |
| Read-only outcomes adapter | `OutcomesStoreAdapter` (intelligence) → `ReadOnlyKnowledgeEvidenceAdapter` (knowledge) → `ReadOnlyRegressionEvidenceAdapter` (regression, **pure alias**) → `ReadOnlyCatalogEvidenceAdapter` (catalog) |

`regression/repository.py` is literally `RegressionEvidenceRepository = KnowledgeEvidenceRepository` plus an empty subclass — evidence that these adapters could collapse into one shared base with per-layer protocols. See [ARCHITECTURE_REPORT](./ARCHITECTURE_REPORT.md) technical-debt TD1 and TD2.

---

## 4. What is genuinely well-bounded

- The **read-only vs core** boundary is real, tested, and (aside from the two documented smells) not violated.
- Route files for the eight downstream layers are cleanly separated (`api/intelligence_routes.py` … `api/comparison_routes.py`) and each import only their own service.
- `schemas` and `config` are pure leaves used by all — no inversion.
