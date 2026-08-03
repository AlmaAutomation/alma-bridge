# Alma Bridge — System Overview

**Status:** Phase 1 Architecture Audit (documentation only — no runtime changes)
**Audit date:** 2026-07-31
**Scope:** `alma_bridge/`, `tests/`, `docs/`
**Companion documents:** [LAYER_DIAGRAM](./LAYER_DIAGRAM.md) · [DEPENDENCY_GRAPH](./DEPENDENCY_GRAPH.md) · [PACKAGE_BOUNDARIES](./PACKAGE_BOUNDARIES.md) · [API_BOUNDARIES](./API_BOUNDARIES.md) · [DATA_FLOW](./DATA_FLOW.md) · [READ_ONLY_BOUNDARIES](./READ_ONLY_BOUNDARIES.md) · [IMPORT_GRAPH](./IMPORT_GRAPH.md) · [ARCHITECTURE_REPORT](./ARCHITECTURE_REPORT.md) · [V1.2_WORK_PLAN](./V1.2_WORK_PLAN.md)

> This document describes what actually exists in the repository as of the audit date. Where the audit brief's assumptions differ from the code, the code is treated as the source of truth and the difference is noted.

---

## 1. What Alma Bridge is

Alma Bridge is a **Windows Compatibility Platform for Linux**, delivered as a single FastAPI application (`alma_bridge/main.py`). It answers one question deterministically: *"what must be true about this host for this Windows application to run correctly?"* — with inspection, a plan, guarded execution, structured verification, and permanent evidence.

The long-form philosophy already lives in [`docs/architecture/alma-bridge-platform-direction.md`](./alma-bridge-platform-direction.md) and is codified in nine ADRs (`docs/adr/ADR-001` … `ADR-009`). This audit set does not restate that philosophy; it maps it onto the **as-built** module structure and grades production readiness.

---

## 2. Runtime shape

- **Process:** one ASGI app (`create_app()` in `alma_bridge/main.py`), served by uvicorn on `127.0.0.1:9010` by default (`alma_bridge/config.py`).
- **Router aggregation:** `alma_bridge/api/routes.py` builds a root `APIRouter` and `include_router`s eight read-only sub-routers (intelligence, graph, knowledge, regression, advisor, ask, catalog, comparison).
- **Background work:** an optional autonomous `operator_loop` (`alma_bridge/operator/`) started in the FastAPI lifespan when `operator_enabled` is set; TLS modernizer bridges (`alma_bridge/compliance/bridge.py`).
- **Persistence:** SQLite. The authoritative evidence store is `data/outcomes.db` (`alma_bridge/storage/outcomes.py`); several subsystems own additional SQLite tables (see [DATA_FLOW](./DATA_FLOW.md)).
- **Config:** `pydantic-settings` in `alma_bridge/config.py`, env prefix `ALMA_BRIDGE_`.

There is **no frontend package in this repository** — the audit brief mentions a "Compatibility Explorer" / UI; today that surface is HTTP JSON APIs plus a CLI (`alma_bridge/cli/shadow_validation.py`) and references to external UIs (`http://127.0.0.1:3001/app/compliance` in the root route). This is documented as a gap, not an omission.

---

## 3. Top-level package map (`alma_bridge/`)

| Package | Py files | Role | Layer (this audit) |
|---------|:---:|------|--------------------|
| `schemas/` | 3 | Pydantic domain + API models (`bridge_domain.py`, `models.py`) | Shared kernel |
| `config.py` | 1 | Settings / feature flags | Shared kernel |
| `storage/` | 2 | `outcomes.db` evidence store (sessions, attempts, stats) | Evidence store |
| `hardware/` | 7 | Host profiling, prefixes, shims, proton | Core support |
| `execution/` | 18 | Wine/Electron process launch, preflight, privileges, shim packs | Execution (core) |
| `bridge/` | 5 | Inspection / profile builder / recent sessions | Execution (core) |
| `session/` | 11 (+5 `services/`) | Lifecycle, policy gate, mutations, verification gateway/engine | Execution + Verification (core) |
| `learning/` | 8 | `BridgeOrchestrator`, ranker, training, datasets | Execution (core) |
| `compatibility/` | 36 | Program kind, framework detection, profiles + shadow validation | Compatibility (core + evidence) |
| `automation/` | 11 | Scan→assess→apply→verify spine, agents, approvals | Execution (core) |
| `operator/` | 5 | Autonomous observe→decide→apply loop | Execution (core) |
| `compliance/` | 15 (+ modernization) | TLS/DNS/drivers/autopilot/modernization playbooks | Execution (core) |
| `importers/` | 5 | Legacy scan/resolve dataset import | Ingestion |
| `validation/` | 7 | Campaign guards, freeze/semantic validators, evidence | Evidence |
| `intelligence/` | 7 | Read-only evidence bundle builder + assessment | Evidence / Intelligence |
| `graph/` | 6 | Read-only compatibility graph (nodes/edges) | Graph |
| `knowledge/` | 6 | Read-only knowledge aggregation | Knowledge |
| `regression/` | 6 | Read-only baseline vs current comparison | Regression |
| `comparison/` | 5 | Read-only environment-aware session diff | Comparison |
| `advisor/` | 7 (+6 `llm/`) | Read-only deterministic explanations (+optional LLM render) | Advisor |
| `ask/` | 9 | Evidence-grounded Q&A | Ask Alma |
| `catalog/` | 5 | Read-only application browser | Catalog (top-level browser) |
| `observability/` | 1 | Prometheus metrics | Cross-cutting |
| `api/` | 11 | FastAPI routers + auth middleware | Interface |
| `cli/` | 1 | Shadow-validation CLI | Interface |
| `flagship.py` | 1 | Flagship program summary metadata | Cross-cutting |

---

## 4. The two-tier authority model (as built)

The codebase realizes the platform-direction "core vs platform" split:

- **Core (execution authority):** `execution`, `session` (+`services`), `bridge`, `learning` (orchestrator), `compatibility` (planner/strategies/profiles), `automation`, `operator`, `compliance`, `hardware`. Only this tier may mutate prefixes, launch processes, and declare `SUCCEEDED` (ADR-001, enforced through `session/verification_gateway.py`).
- **Read-only evidence consumers (downstream):** `intelligence` → `graph` → `knowledge` → `regression` → `comparison` → `advisor` → `ask`, plus `catalog` as a cross-cutting browser. These consume persisted evidence from `outcomes.db` and never enter the execution authority boundary.

Every read-only package ships a dedicated **architecture-boundary test** (e.g. `tests/advisor/test_advisor_architecture_boundaries.py`, `tests/comparison/test_comparison_architecture_boundaries.py`) that fails the build if the package imports `orchestrator`, `verification_gateway`, `session.mutations`, `winetricks`, or `ActionIntent`, and asserts routes are read-only. This is a notable strength — the boundary is executable, not just documented.

---

## 5. Requested layer order vs. reality

The audit brief specifies a strictly downstream chain:

```
Execution → Verification → Evidence → Compatibility Graph → Knowledge → Regression → Comparison → Advisor → Ask Alma   (+ Catalog as top-level browser)
```

This chain is **substantially accurate** for the read-only tier. Package imports flow strictly downstream (no read-only package imports the orchestrator / execution). The two nuances found:

1. `graph`, `knowledge`, `regression`, `comparison`, `advisor`, `ask`, `catalog` all depend on `intelligence` (directly or transitively) as the shared **Evidence** substrate — `intelligence.EvidenceBundleBuilder` is the single evidence-assembly primitive reused by `catalog` and `comparison`.
2. `knowledge` and `comparison` import one pure predicate (`aggregate_verification_passed`) from the **core** package `session.stop_on_success_verification`. This is the only source-level edge from the read-only tier into a core package. It is not a control-flow violation (the function performs no I/O), but it is a layering smell — see [READ_ONLY_BOUNDARIES](./READ_ONLY_BOUNDARIES.md).

---

## 6. Test posture

- 116 `test_*.py` files (127 python files total under `tests/`), including package-scoped suites for each read-only layer plus core suites (`test_orchestrator_authority.py`, `test_verification_authority.py`, `test_architecture_invariants.py`, `test_suite_isolation.py`).
- Architecture is defended by tests, not just prose — see [READ_ONLY_BOUNDARIES](./READ_ONLY_BOUNDARIES.md).
- Known test-isolation debt is tracked in `docs/reviews/full-suite-test-isolation-triage.md`.

See [ARCHITECTURE_REPORT](./ARCHITECTURE_REPORT.md) for strengths, risks, and recommendations, and [V1.2_WORK_PLAN](./V1.2_WORK_PLAN.md) for the phased plan.
