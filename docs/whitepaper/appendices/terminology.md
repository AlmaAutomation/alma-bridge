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
| **Read-only platform tier** | Packages that consume evidence only: intelligence, graph, knowledge, regression, comparison, advisor, ask, catalog, decision | `docs/architecture/READ_ONLY_BOUNDARIES.md` |
| **Decision Engine** | Read-only deterministic plan recommendations from composed evidence (`decision/`) | ADR-010 |
| **Decision Plan Review** | Append-only human approval bound to canonical plan digest (`decision_review/`) | ADR-011 |
| **Decision Plan Validation** | Non-executing dry-run feasibility reports for approved plans (`decision_validation/`) | ADR-012 |
| **plan_digest** | SHA-256 canonical serialization of plan content excluding `generated_at`; binds approvals | ADR-011 |
| **DecisionPlanDryRunReport** | Observational validation artifact with `execution_performed=false`, `mutations_performed=false` | ADR-012 |
| **ActionIntent** | Typed mutation request evaluated by `PolicyGate` before prefix or runtime changes | ADR-001 |
| **CompatibilityProfile (shadow)** | Predictive profile subsystem that does not apply to execution when reuse is disabled | `compatibility/profile_shadow*.py`, platform-direction doc |
| **Statically predicted** | Pre-execution ACI compatibility assessment from read-only PE analysis — not verified | `compatibility_intelligence/`, ADR-017 |
| **Behaviorally covered** | Required API behavior profile is supported by the provider — distinct from symbol coverage | `compatibility_intelligence/behavior_requirements.py`, ADR-017 |
| **Authoritatively verified** | Outcome declared by VerificationEngine through VerificationGateway | ADR-001, ADR-017 |
| **Prediction confirmed** | Calibration classification `true_positive` or `true_negative` | ADR-017 |
| **Prediction contradicted** | Calibration classification `false_positive` or `false_negative` | ADR-017 |
| **PredictionSnapshot** | Immutable pre-execution ACI prediction bound to binary digest and registry versions | `compatibility_intelligence/calibration_repository.py`, ADR-017 |
| **outcomes.db** | Authoritative SQLite store for `bridge_sessions` and `bridge_attempts` | `storage/outcomes.py` |
| **Plugin** | **Future work:** proposed extensibility for detectors, planners, verifiers — design-only | `docs/architecture/plugin-architecture.md` |
| **Compatibility Explorer** | External UI in **almasysdet** providing session exploration, decision plan review, and dry-run validation | `almasysdet` Explorer components |
