# Alma Bridge v1.2 — Architecture Report (Phase 1 Audit)

**Status:** Phase 1 Architecture Audit — documentation only, no runtime changes
**Audit date:** 2026-07-31
**Auditor scope:** `alma_bridge/` (23 top-level packages, ~219 modules), `tests/` (116 test files), `docs/`
**Verdict headline:** The execution-authority / read-only-evidence split is **real, tested, and not violated**. Production-readiness risk is concentrated in the **core cluster** (tangled imports, no shared persistence layer) and in **duplication** across the read-only tier — not in boundary breaches.

---

## 1. Strengths

1. **Executable architecture boundaries.** Every read-only layer (`intelligence`, `graph`, `knowledge`, `regression`, `comparison`, `advisor`, `ask`, `catalog`) has a dedicated boundary test that fails the build on forbidden imports and non-GET routes. Architecture is enforced, not merely aspirational. (`tests/*/test_*architecture_boundaries.py`)
2. **A single authoritative success rule.** `SUCCEEDED` flows through exactly one path — `session/verification_gateway.py` gated by `DefaultVerificationEngine` — and both write and read paths agree on `aggregate_verification_passed()`. `exit_code==0` is explicitly not success (ADR-001/002).
3. **Documented intent that matches the code.** Nine ADRs plus `alma-bridge-platform-direction.md` describe the core/platform split; the as-built packages line up with the documented layers.
4. **A shared evidence primitive.** `intelligence.EvidenceBundleBuilder` gives every read-only layer one consistent, versioned view of persisted evidence with typed provenance references.
5. **Guardrails on mutating endpoints.** Campaign guard on `/bridge/run`, `allow_mutations`/approval-token gates on modernization + automation, API-key middleware, prefix locks + policy gate for mutations.
6. **Deep test coverage of the core loop.** Orchestrator authority, verification authority, stop-on-success, session lease/lifecycle, and per-layer suites all exist.

---

## 2. Top risks (production readiness)

| ID | Risk | Severity | Evidence | Consequence |
|----|------|:--------:|----------|-------------|
| **R1** | **No shared persistence layer.** ~20 modules each call `sqlite3.connect(...)` and own ad-hoc schema/migrations; read-only adapters reach into `outcomes._connect()` private internals. | High | `storage/outcomes.py`, `compatibility/profile_*`, `automation/*`, `compliance/*`, `intelligence/repository.py:46` | Schema drift, migration races, concurrent-write locking, hard to back up/observe as one system |
| **R2** | **Tangled core with 11 mutual import cycles**, resolved only by function-local imports. | High | `execution↔session↔bridge↔learning↔compatibility↔compliance↔automation↔validation` (see IMPORT_GRAPH §5) | Fragile startup ordering, hidden coupling, refactors ripple unpredictably |
| **R3** | **Monolithic surfaces.** `api/routes.py` = 1,255 lines / 7 tag groups; `storage/outcomes.py` = 967 lines; `compatibility/` = 36 modules (many `profile_shadow_*` variants). | Medium-High | file sizes/counts | High change-risk, review fatigue, merge conflicts |
| **R4** | **Boundary guard list is incomplete & copy-pasted.** `FORBIDDEN_IMPORT_FRAGMENTS` omits `planner`, `remediation`, `execution.`, `automation`, `operator`; duplicated in each test. | Medium | `tests/*/test_*architecture_boundaries.py` | A future regression importing the planner/execution would pass the guard |
| **R5** | **Open-by-default auth + hardcoded dev CORS.** `api_key=None` leaves mutating endpoints open; CORS pins `:9002/:3000/:3001`. | Medium | `config.py:61`, `main.py:72-85` | Unsafe if deployed beyond localhost without config |
| **R6** | **Read→core pure-predicate edge.** `knowledge` and `comparison` import `session.stop_on_success_verification`. | Low-Medium | `knowledge/aggregation.py:24`, `comparison/queries.py:15` | Normalizes crossing the read/core line; not caught by guards |
| **R7** | **Test-isolation debt.** Full-suite isolation issues already triaged. | Medium | `docs/reviews/full-suite-test-isolation-triage.md`, `tests/test_suite_isolation.py`, `scripts/find_polluters.py` | Flaky CI, shared-DB bleed between tests |
| **R8** | **Application identity = `file_hash` equality.** No program-identity graph key yet. | Medium | `intelligence/repository.py` `list_sessions_for_fingerprint` | Same app across versions/paths may not correlate; Advisor/Catalog completeness limited |

---

## 3. Technical debt inventory

| ID | Debt | Location | Suggested remedy |
|----|------|----------|------------------|
| **TD1** | Six near-identical `*NotFoundError` + four `Malformed*` error types across read-only packages | `*/models.py` | One shared `evidence/errors.py` base hierarchy |
| **TD2** | Four `ReadOnly*EvidenceAdapter` classes, one a pure alias | `intelligence/knowledge/regression/catalog repository.py` | Collapse to one adapter + per-layer `Protocol` |
| **TD3** | Framework-detection heuristics duplicated | `compatibility/framework_detection.py` vs `intelligence/evidence.py:254` | Read path should consume persisted detector output, not re-derive |
| **TD4** | Two provenance/reference model types bridged by a private method | `intelligence/models.py`, `knowledge/models.py`, `comparison/queries.py:274` | Unify on one `EvidenceReference`; make the mapper public |
| **TD5** | Private-member access across packages (`_connect`, `_to_knowledge_ref`) | `intelligence/repository.py`, `comparison/queries.py` | Public read APIs |
| **TD6** | `CompatibilityBridgePlan` schema exists but is not wired as orchestrator input (planner role split) | `schemas/bridge_domain.py` vs `session/services/planner.py`, `learning/orchestrator.py` | Converge planners (already flagged in platform-direction doc) |
| **TD7** | App-specific legacy branches (e.g. Ascension) in core | `compatibility/ascension_layout.py`, remediation entries | Migrate to plugins (platform-direction §"Expand plugin boundaries") |
| **TD8** | `api/routes.py` handlers use function-local imports to dodge cycles | `api/routes.py` | Falls out of R2 fix + router split |

---

## 4. Recommendations (top 5, prioritized)

1. **Introduce a persistence/repository layer (addresses R1, R6, TD2, TD5).** A single `alma_bridge/storage/` gateway that owns all SQLite connections and exposes read-only query interfaces. Read-only adapters consume it; no more `_connect()` leaks. This is the highest-leverage production-readiness move.
2. **Split the two monoliths (addresses R3, R8-adjacent, TD8).** Break `api/routes.py` into tag-scoped routers (mirroring the already-split read-only routers) and decompose `storage/outcomes.py` into `schema/`, `sessions`, `attempts`, `stats`.
3. **Harden and centralize the read-only boundary guard (addresses R4, R6).** One shared forbidden-fragment list including `planner`/`remediation`/`execution.`/`automation`/`operator`; a meta-test that every read-only package is covered; relocate the verification predicate out of `session`.
4. **Break the core cycles incrementally (addresses R2).** Extract shared leaf modules (types, verification semantics, prefix constants) so `execution`/`session`/`bridge`/`learning`/`compatibility` depend on leaves, not each other. Track by counting remaining mutual cycles.
5. **De-duplicate the evidence/read-only tier (addresses TD1–TD4).** Shared error hierarchy, one `EvidenceReference`, one adapter, read-path consumes persisted framework detections instead of re-deriving.

---

## 5. Critical boundary violations found

**None.** The Phase-1 invariant (read-only tier must not touch execution authority) holds. The only findings are:
- **2 smells** — pure-predicate imports of `session.stop_on_success_verification` by `knowledge` and `comparison` (R6).
- **3 encapsulation leaks** — cross-package private access (TD5).

Neither category grants the read-only tier the ability to mutate prefixes, launch processes, or declare success.

---

## 6. Production-readiness scorecard

| Dimension | Grade | Rationale |
|-----------|:-----:|-----------|
| Boundary integrity (read-only vs core) | A- | Enforced by tests; 2 documented smells |
| Core cohesion / coupling | C | 11 mutual cycles, deferred-import workarounds |
| Persistence architecture | C- | No shared layer; private access; ad-hoc schemas |
| API structure | C+ | Read-only routers clean; core `routes.py` monolithic |
| Duplication / DRY | C+ | Errors, adapters, provenance, framework logic duplicated |
| Test coverage & enforcement | B+ | Broad, architecture-aware; isolation debt outstanding |
| Documentation | A | ADRs + platform-direction + this audit set |
| Security posture (deploy) | C+ | Guardrails exist; open-by-default auth needs config discipline |

See [V1.2_WORK_PLAN](./V1.2_WORK_PLAN.md) for the phased execution plan (Phases 2–10).
