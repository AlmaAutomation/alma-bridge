# Alma Bridge Subsystems

| Subsystem | Purpose | Authority | Input | Output | Mutability |
|-----------|---------|-----------|-------|--------|------------|
| `schemas/` | Shared Pydantic domain and API models | Referenced by all layers | JSON / Python types | Validated structures | Immutable at runtime |
| `config.py` | Settings and feature flags (`ALMA_BRIDGE_*`) | Configuration | Environment variables | `settings` object | Read at startup |
| `hardware/` | Host profiling, Wine prefixes, shims, Proton discovery | Core support (read host; recommend shims) | sysfs, `/proc`, Steam paths | `HardwareProfile`, shim recommendations | Read-only probes; no prefix mutation |
| `bridge/` | Application inspection and recent session views | Core (inspection only on read paths) | File path | `CompatibilityInspection`, session summaries | Inspection reads files; no execution |
| `execution/` | Process launch (Wine, Proton, Electron, container) | Core execution | Plan, env, command | `ExecutionResult`, exit codes | Mutates process state; container runs |
| `session/` | Lifecycle state machine, policy gate, prefix mutations, verification gateway | Core + verification authority | `ActionIntent`, attempt records | State transitions, verified success | Mutates session DB rows, prefixes (gated) |
| `learning/` | `BridgeOrchestrator`, strategy ranker, training datasets | Core lifecycle owner | `BridgeRequest` | Session results, rerank events | Writes outcomes; orchestrates retries |
| `compatibility/` | Program kind, framework detection, profiles, shadow validation | Core planning + evidence capture | Inspection, attempts | Plans, profile candidates, shadow metrics | Writes profile stores; shadow is non-authoritative |
| `automation/` | Unified scan→assess→playbook→apply→verify spine | Core (host modernization + optional bridge run) | Playbook recipe, approval token | Automation audit sessions | Mutates host when `apply=true` (gated) |
| `operator/` | Autonomous observe→decide→apply loop | Core (optional background) | Operator tick requests | Remediation plans | Mutates when enabled and ticked |
| `compliance/` | TLS/DNS/drivers/autopilot/modernization playbooks | Core (mixed read/write) | Host targets, error text | Assessments, TLS bridges, pathways | Mixed; apply paths mutate host |
| `importers/` | Import almasysdet and alma_resolve history | Ingestion | External SQLite / audit dirs | Rows in `outcomes.db` | Writes import log + sessions |
| `validation/` | Campaign guards, freeze/semantic validators | Evidence gatekeeping | Bridge requests, campaign config | Validation errors / evidence artifacts | Writes campaign evidence stores |
| `storage/outcomes.py` | Authoritative session and attempt store | Evidence persistence | Orchestrator writes | `bridge_sessions`, `bridge_attempts` | Write on core path; read on platform path |
| `intelligence/` | Evidence bundle assembly and compatibility assessment | Read-only platform | Persisted DB rows | `EvidenceBundle`, `CompatibilityAssessment` | Read-only |
| `graph/` | Evidence-derived compatibility graph | Read-only platform | `EvidenceBundle` | `GraphNode`, `GraphEdge`, subgraphs | Writes graph tables only on ingestion; no execution |
| `knowledge/` | Cross-session knowledge aggregation | Read-only platform | `EvidenceBundle` | `CompatibilityKnowledgeProfile` | Computed on read (Phase 1); no KB tables |
| `regression/` | Baseline vs current profile comparison | Read-only platform | Knowledge profiles | `CompatibilityRegressionReport` | Pure diff; no writes |
| `comparison/` | Session-pair environment and outcome diff | Read-only platform | Two session snapshots | `SessionEnvironmentComparison` | Pure diff; no writes |
| `advisor/` | Deterministic (+ optional LLM) explanations | Read-only platform | Knowledge + regression context | `AdvisorExplanation` | No persistence |
| `ask/` | Evidence-grounded Q&A | Read-only platform | Natural-language question + fingerprint | `AskAlmaAnswer` | POST is read-only (no DB writes) |
| `catalog/` | Application browser aggregate | Read-only platform | All fingerprints | `CompatibilityCatalogResponse` | Read-only |
| `api/` | FastAPI routers and auth middleware | Interface | HTTP | JSON responses | Delegates mutability to handlers |
| `cli/` | Shadow validation CLI | Interface | Campaign config | Reports, gate results | Writes shadow validation store |
| `observability/` | Prometheus metrics | Cross-cutting | Internal counters | `/metrics` text | Read-only export |

**Sources:** `docs/architecture/SYSTEM_OVERVIEW.md`, `docs/architecture/LAYER_DIAGRAM.md`, `docs/architecture/DATA_FLOW.md`, Phase 1 audit (2026-07-31).
