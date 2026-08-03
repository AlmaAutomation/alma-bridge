# Alma Bridge — Import Graph (Phase 1, with file evidence)

**Status:** Phase 1 Architecture Audit (documentation only)
**Method:** AST scan of every `alma_bridge/**/*.py`. This document records *actual* import relationships with file-path evidence and flags violations/smells explicitly.
**Companion:** [DEPENDENCY_GRAPH](./DEPENDENCY_GRAPH.md) (aggregated edges) · [READ_ONLY_BOUNDARIES](./READ_ONLY_BOUNDARIES.md)

---

## 1. Read-only tier — inbound evidence dependency (with evidence)

| Consumer file | Imports | Evidence |
|---------------|---------|----------|
| `catalog/service.py` | `intelligence.evidence.EvidenceBundleBuilder` | line 8 |
| `catalog/service.py` | `catalog.repository.ReadOnlyCatalogEvidenceAdapter` | line 7 |
| `comparison/service.py` | `intelligence.evidence.EvidenceBundleBuilder` | line 13 |
| `comparison/service.py` | `knowledge.repository.ReadOnlyKnowledgeEvidenceAdapter` | line 16 |
| `comparison/queries.py` | `intelligence.models`, `knowledge.aggregation`, `knowledge.models`, `knowledge.queries`, `graph.queries`, `compatibility.run_environment` | lines 9–14 |
| `advisor/service.py` | `regression.repository.ReadOnlyRegressionEvidenceAdapter`, `regression.models` | lines 19–20 |
| `advisor/service.py` | `advisor.context`, `advisor.explanation`, `advisor.llm.*` | lines 7–10 |
| `ask/service.py` | `ask.answer`, `ask.classifier`, `ask.context`, `ask.models` | lines 5–8 |
| `regression/repository.py` | `knowledge.repository` (alias `RegressionEvidenceRepository = KnowledgeEvidenceRepository`) | lines 5–10 |
| `knowledge/repository.py` | `intelligence.repository.OutcomesStoreAdapter` | line 7 |
| `intelligence/repository.py` | `storage.outcomes`, `compatibility.profile_store`, `compatibility.profile_shadow_store` | lines 9–17 |

This confirms the downstream chain **Evidence(intelligence) → Graph → Knowledge → Regression → Comparison → Advisor → Ask**, with **Catalog** consuming Evidence + Knowledge + Regression directly.

---

## 2. Cross-tier edges (read-only → core) — the ONLY ones

| Consumer | Import statement | File:line | Classification |
|----------|------------------|-----------|----------------|
| `knowledge/aggregation.py` | `from alma_bridge.session.stop_on_success_verification import aggregate_verification_passed` | `knowledge/aggregation.py:24` | **Smell** — pure predicate from core `session` |
| `comparison/queries.py` | `from alma_bridge.session.stop_on_success_verification import aggregate_verification_passed` | `comparison/queries.py:15` | **Smell** — same |

No other read-only file imports anything from `execution`, `session.mutations`, `session.verification_gateway`, `learning.orchestrator`, `automation`, `operator`, or `compliance`. **No forbidden-import violations exist.**

---

## 3. Encapsulation / private-access edges (with evidence)

| Consumer | Access | File:line |
|----------|--------|-----------|
| `intelligence/repository.py` | `outcomes._connect()` (private) | `intelligence/repository.py:46` (`# noqa: SLF001`) |
| `intelligence/repository.py` | `from alma_bridge.compatibility.profile_store import _connect as profile_connect` | `intelligence/repository.py:13-16` |
| `comparison/queries.py` | `KnowledgeAggregationEngine()._to_knowledge_ref(ref, artifact)` (private) | `comparison/queries.py:274` (`# noqa: SLF001`) |

---

## 4. Duplicated derivation logic (with evidence)

| Logic | Location A | Location B | Note |
|-------|-----------|-----------|------|
| Framework detection (wxWidgets/Qt heuristics) | `compatibility/framework_detection.py` (core detector) | `intelligence/evidence.py:254-301` `_framework_from_attempt` | Evidence builder re-derives frameworks from stderr/stdout string matches |
| Evidence reference type | `intelligence/models.py` `EvidenceReference` | `knowledge/models.py` `KnowledgeEvidenceReference` | Two provenance types bridged by a private method |
| Read-only outcomes adapter | `intelligence/repository.py` `OutcomesStoreAdapter` | `knowledge/repository.py`, `regression/repository.py`, `catalog/repository.py` subclasses | Regression subclass is an empty alias |
| Verification-pass predicate consumers | `knowledge/aggregation.py` | `comparison/queries.py` | Both import the same `session` predicate (see §2) |

---

## 5. Core-tier cycles (with mechanism)

The following mutual import cycles exist at package granularity and are resolved at runtime via **deferred (function-local) imports**:

| Cycle | Break mechanism (evidence) |
|-------|-----------------------------|
| `storage ↔ compatibility` | `storage/outcomes.py:22-23` imports `compatibility.profile_shadow` / `profile_store` **inside** `init_outcome_store()` |
| `__root__ ↔ operator` | `main.py:18,25` imports `operator.operator_loop` **inside** `_lifespan` |
| `__root__ ↔ (planner/operator/privileges)` | `api/routes.py` imports planner (line 282-283), operator (988, 998, …), privileges (1014) **inside** handlers |
| `execution ↔ session`, `learning ↔ session`, `compatibility ↔ session`, `bridge ↔ session`, `execution ↔ bridge/compliance/compatibility/learning`, `compliance ↔ automation`, `compatibility ↔ validation` | mix of module-level and deferred imports across the core |

These are structural (the core is a tightly coupled cluster), not accidental; they do not affect the read-only tier. See [ARCHITECTURE_REPORT](./ARCHITECTURE_REPORT.md) R2.

---

## 6. Machine-checkable summary

- Read-only → core forbidden-import violations: **0**
- Read-only → core pure-predicate edges (smell): **2** (`knowledge`, `comparison`)
- Cross-package private-member accesses: **3**
- Confirmed mutual (2-node) core cycles: **11**
- Packages importing `api`: **0** (api is a pure sink) ✅
- `api` fan-out: **24** packages
