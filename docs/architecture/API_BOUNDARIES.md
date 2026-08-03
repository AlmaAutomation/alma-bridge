# Alma Bridge — API Boundaries

**Status:** Phase 1 Architecture Audit (documentation only)
**Source:** `alma_bridge/api/` (11 modules) + `alma_bridge/main.py`
**Companion:** [READ_ONLY_BOUNDARIES](./READ_ONLY_BOUNDARIES.md) · [SYSTEM_OVERVIEW](./SYSTEM_OVERVIEW.md)

---

## 1. Composition

`alma_bridge/main.py::create_app()` builds the FastAPI app, adds CORS + `ApiKeyMiddleware` (`alma_bridge/api/auth.py`), and includes the root router from `alma_bridge/api/routes.py`. `routes.py` in turn mounts eight read-only sub-routers:

```
router.include_router(intelligence_router)   # api/intelligence_routes.py
router.include_router(graph_router)          # api/graph_routes.py
router.include_router(knowledge_router)      # api/knowledge_routes.py
router.include_router(regression_router)     # api/regression_routes.py
router.include_router(advisor_router)        # api/advisor_routes.py
router.include_router(ask_router)            # api/ask_routes.py
router.include_router(catalog_router)        # api/catalog_routes.py
router.include_router(comparison_router)     # api/comparison_routes.py
```

---

## 2. Read-only (evidence) API surface — GET-only except Ask

| Layer | Endpoint(s) | Method | Handler module |
|-------|-------------|:------:|----------------|
| Intelligence | `/bridge/intelligence/sessions/{session_id}`<br>`/bridge/intelligence/applications/{fingerprint}` | GET | `intelligence_routes.py` |
| Graph | `/bridge/graph/applications/{fingerprint}`<br>`/bridge/graph/sessions/{session_id}`<br>`/bridge/graph/nodes/{node_id}`<br>`/bridge/graph/edges/{edge_id}` | GET | `graph_routes.py` |
| Knowledge | `/bridge/knowledge/applications/{fingerprint}` | GET | `knowledge_routes.py` |
| Regression | `/bridge/regression/applications/{fingerprint}`<br>`/bridge/regression/sessions/{session_id}` | GET | `regression_routes.py` |
| Comparison | `/bridge/comparison/sessions/{baseline_session_id}/{comparison_session_id}`<br>`/bridge/comparison/applications/{fingerprint}` | GET | `comparison_routes.py` |
| Advisor | `/bridge/advisor/applications/{fingerprint}`<br>`/bridge/advisor/sessions/{session_id}` | GET | `advisor_routes.py` |
| Ask Alma | `/bridge/ask` | **POST** | `ask_routes.py` |
| Catalog | `/bridge/catalog/applications` | GET | `catalog_routes.py` |

**Ask Alma is the only read-only layer that uses POST**, because it accepts a question body (`AskAlmaQuestion`). It performs no writes; its boundary test does not assert GET-only (it asserts no forbidden imports). All other read-only layers are strictly GET and their boundary tests assert every route decorator is `.get`.

### Enforced read-only invariants (per test)
For advisor / comparison (and equivalently the other layers), `tests/*/test_*architecture_boundaries.py` assert:
1. No package file imports `orchestrator`, `verification_gateway`, `session.mutations`, `winetricks`, `ActionIntent`.
2. The route module is GET-only.
3. Importing the route module does **not** import `alma_bridge.learning.orchestrator` (`sys.modules` check).
4. A GET request does not trigger graph ingestion / `record_attempt` (advisor).

---

## 3. Core (execution authority) API surface — the mutating side

All of the following live in the monolithic `alma_bridge/api/routes.py`:

| Tag | Representative endpoints | Mutating? |
|-----|--------------------------|:---------:|
| System | `/`, `/health`, `/metrics`, `/flagship`, `/prefixes` | no |
| Hardware | `/hardware/profile` | no |
| Bridge | `/bridge/inspect`, `/bridge/program\|installer\|launcher/preflight`, `/bridge/plan` | no |
| Bridge | `/bridge/run`, `/bridge/run/async`, `/bridge/run/{id}/result`, `/bridge/session/{id}`, `/bridge/sessions/recent` | **yes** (run) |
| Learning | `/outcomes/stats`, `/outcomes/prior-success` | no |
| Import | `/import/all`, `/import/sysdet`, `/import/resolve` | **yes** |
| Training | `/train/ranker`, `/datasets/export` | **yes** |
| Compliance | `/compliance/tls/*`, `/compliance/dns/*`, `/compliance/drivers`, `/compliance/scan`, `/compliance/autopilot/*`, `/compliance/legacy32*`, `/compliance/program*` | mixed |
| Modernization | `/modernization/*`, `/modernization/windows/*` | **yes** (apply) |
| Automation | `/automation/run`, `/automation/agent/*`, `/automation/approve` | **yes** |
| Operator | `/operator/tick`, `/operator/remediate`, `/operator/start\|stop`, `/operator/plan\|observe\|routes\|failures` | **yes** (tick/remediate) |
| Compatibility | `/compatibility/make-work`, `/compatibility/shadow/validation/report\|gates` | make-work: **yes** |
| Container | `/container/run`, `/container/shim-pack`, `/execution/sudo/*` | **yes** |

### Guardrails observed on mutating endpoints
- `/bridge/run` and `/bridge/run/async` call `validate_campaign_bridge_request` and raise `403` on campaign-prefix rejection (`alma_bridge/validation/campaign_guard.py`).
- `/modernization/apply` requires `allow_mutations=true` (else `400`).
- `/automation/run` requires `allow_mutations` or a valid `approval_token` when `apply` is set.
- `ApiKeyMiddleware` gates mutating endpoints when `settings.api_key` is set (open for local dev by default — see risk R5 in the report).

---

## 4. API boundary risks

| ID | Finding | Impact |
|----|---------|--------|
| A1 | `api/routes.py` is 1,255 lines spanning 7 unrelated tag groups | High change-risk; hard to review; encourages cross-domain coupling |
| A2 | Many handlers use function-local imports (planner, operator, privileges) to dodge import cycles | Hides the dependency graph; startup cost moved to first-request |
| A3 | Default `api_key = None` → mutating endpoints open on localhost | Fine for dev; must be set for any shared/prod deployment |
| A4 | CORS allow-list hardcodes `:9002/:3000/:3001` dev origins | Deploy-time config, not code, would be cleaner |
| A5 | Ask uses POST while peers use GET | Acceptable (body needed) but document explicitly so it is not mistaken for a write endpoint |

Splitting `routes.py` into tag-scoped routers (mirroring the already-split read-only routers) is Phase 2 of the [work plan](./V1.2_WORK_PLAN.md).
