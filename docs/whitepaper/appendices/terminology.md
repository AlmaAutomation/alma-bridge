# Terminology

| Term | Definition | Source |
|------|------------|--------|
| **Alma Bridge** | Windows Compatibility Platform for Linux: FastAPI service (`alma_bridge/main.py`) that inspects, plans, executes, verifies, and persists compatibility evidence | `docs/architecture/SYSTEM_OVERVIEW.md` |
| **Alma Automation** | Unified host modernization pipeline: scan → assess → playbook → apply → verify, implemented in `alma_bridge/automation/` | `automation/runner.py` docstring |
| **Binary Compatibility Scanner** | External **almasysdet** project performing binary scanning and static rules; Bridge imports its history via `importers/sysdet.py`. Bridge-local inspection: `GET /bridge/inspect` | `README.md` relationship table |
| **BridgeOrchestrator** | Sole lifecycle owner for `POST /bridge/run` (`learning/orchestrator.py`) | ADR-001 |
| **VerificationGateway** | Sole path to session state `SUCCEEDED` and `finalize_session(success=True)` | ADR-001, `session/verification_gateway.py` |
| **VerificationEngine** | Aggregates execution evidence into structured `VerificationResult`; owns verification semantics | ADR-001, `session/services/verification.py` |
| **Aggregate verification pass** | `aggregate_verification_passed()` returns True only when versioned policy (e.g. `bridge_aggregate_v1`) passes on persisted verification JSON | `session/stop_on_success_verification.py` |
| **EvidenceBundle** | Versioned assembly of typed `EvidenceReference` records and keyed artifacts from persisted sessions | `intelligence/evidence.py`, ADR-002 |
| **Application fingerprint** | Currently `bridge_sessions.file_hash` (content hash equality), not a full program-identity graph key | `docs/architecture/DATA_FLOW.md` §2 |
| **Compatibility Graph** | Read-only nodes and edges materialized from evidence with mandatory provenance (`graph/`) | ADR-003 |
| **Compatibility Knowledge Profile** | Cross-session aggregation of framework observations, strategy rates, environments (`knowledge/`) | ADR-004 |
| **Regression report** | Diff between baseline knowledge profile (excluding comparison session) and current profile | ADR-005 |
| **Session comparison** | Pairwise diff of two sessions for the same fingerprint including environment fields | ADR-009, `comparison/` |
| **Read-only platform tier** | Packages that consume evidence only: intelligence, graph, knowledge, regression, comparison, advisor, ask, catalog | `docs/architecture/READ_ONLY_BOUNDARIES.md` |
| **ActionIntent** | Typed mutation request evaluated by `PolicyGate` before prefix or runtime changes | ADR-001 |
| **CompatibilityProfile (shadow)** | Predictive profile subsystem that does not apply to execution when reuse is disabled | `compatibility/profile_shadow*.py`, platform-direction doc |
| **outcomes.db** | Authoritative SQLite store for `bridge_sessions` and `bridge_attempts` | `storage/outcomes.py` |
| **Plugin** | **Future work:** proposed extensibility for detectors, planners, verifiers — design-only | `docs/architecture/plugin-architecture.md` |
| **Compatibility Explorer** | **Future work / external UI:** referenced in platform direction; no frontend in alma-bridge repo | `docs/architecture/SYSTEM_OVERVIEW.md` §2 |
