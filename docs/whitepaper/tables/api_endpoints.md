# Alma Bridge API Endpoints

Derived from `alma_bridge/api/routes.py` and read-only sub-routers as of Phase 1 audit (2026-07-31). Side effects indicate whether the endpoint mutates host state, persistent stores, or running processes.

## Read-only platform tier

| Endpoint | Method | Purpose | Side Effects |
|----------|--------|---------|--------------|
| `/bridge/intelligence/sessions/{session_id}` | GET | Compatibility assessment for one session | None (reads DB) |
| `/bridge/intelligence/applications/{fingerprint}` | GET | Compatibility assessment for application fingerprint | None |
| `/bridge/graph/applications/{fingerprint}` | GET | Application compatibility subgraph | Idempotent graph ingestion writes graph tables only |
| `/bridge/graph/sessions/{session_id}` | GET | Session-scoped subgraph | Idempotent graph ingestion |
| `/bridge/graph/nodes/{node_id}` | GET | Single graph node lookup | None |
| `/bridge/graph/edges/{edge_id}` | GET | Single graph edge lookup | None |
| `/bridge/knowledge/applications/{fingerprint}` | GET | Cross-session knowledge profile | None (computed on read) |
| `/bridge/regression/applications/{fingerprint}` | GET | Regression report vs baseline | None |
| `/bridge/regression/sessions/{session_id}` | GET | Session-scoped regression report | None |
| `/bridge/comparison/sessions/{baseline}/{comparison}` | GET | Pairwise session comparison | None |
| `/bridge/comparison/applications/{fingerprint}` | GET | Session comparison with query params | None |
| `/bridge/advisor/applications/{fingerprint}` | GET | Deterministic advisor explanation | None; optional LLM network call if configured |
| `/bridge/advisor/sessions/{session_id}` | GET | Session-scoped advisor explanation | None; optional LLM |
| `/bridge/ask` | POST | Evidence-grounded Q&A | None (no persistence); optional LLM |
| `/bridge/catalog/applications` | GET | Application catalog listing | None |
| `/bridge/compatibility/analyze` | POST | PE capability analysis and prediction (read-only) | Writes analysis JSON to data dir when persist=true |
| `/bridge/compatibility/history` | GET | Recent compatibility analyses | None |
| `/bridge/compatibility/analysis/{digest}` | GET | Analysis by binary digest | None |
| `/bridge/compatibility/capabilities` | GET | Capability registry | None |
| `/bridge/compatibility/apis` | GET | API classification registry | None |
| `/bridge/compatibility/metrics` | GET | Registry metrics | None |
| `/bridge/compatibility/predict` | GET | Quick prediction from file path (read-only) | None |
| `/bridge/compatibility/calibration` | GET | Prediction calibration metrics with sample sizes | None |
| `/bridge/compatibility/calibration/capabilities/{capability_id}` | GET | Per-capability calibration evidence | None |
| `/bridge/compatibility/calibration/analyses/{analysis_digest}` | GET | Calibration records for an analysis digest | None |
| `/bridge/compatibility/governance/proposals` | GET | List capability promotion proposals | None |
| `/bridge/compatibility/governance/proposals/{proposal_id}` | GET | Promotion proposal detail | None |
| `/bridge/compatibility/governance/registry` | GET | Current versioned capability maturity registry | None |
| `/bridge/compatibility/governance/registry/versions` | GET | Registry version history | None |
| `/bridge/compatibility/expansion/plan` | GET | Ranked runtime expansion engineering plan (advisory) | None |
| `/bridge/compatibility/expansion/candidates/{candidate_id}` | GET | Single expansion candidate detail | None |
| `/bridge/evidence/bundles/{binary_digest}` | GET | Evidence bundle by binary digest | Writes bundle on first assemble |
| `/bridge/evidence/applications/{fingerprint}` | GET | Evidence bundle by application fingerprint | Writes bundle on first assemble |
| `/bridge/evidence/bundles/{bundle_id}/timeline` | GET | Immutable lifecycle timeline | None |
| `/bridge/evidence/bundles/{bundle_id}/history` | GET | Historical bundle versions | None |
| `/bridge/evidence/platform/health` | GET | Platform health metrics with sample sizes | None |
| `/bridge/evidence/assemble` | POST | Assemble bundle from subsystem artifacts | Writes bundle |

## Decision pipeline (Phases 1–3)

| Endpoint | Method | Purpose | Side Effects |
|----------|--------|---------|--------------|
| `/bridge/decision/plan` | GET, POST | Deterministic decision plan from session/fingerprint | None |
| `/bridge/decision/plans/{plan_id}` | GET | Plan detail with digest and summary | None |
| `/bridge/decision/plans/{plan_id}/reviews` | GET, POST | Review history / submit review | POST writes review row |
| `/bridge/decision/plans/{plan_id}/review/latest` | GET | Latest review for plan | None |
| `/bridge/decision/plans/{plan_id}/export` | POST | Export JSON or Markdown artifact | Writes export row |
| `/bridge/decision/plans/{plan_id}/validate` | POST | Non-executing dry-run validation | Writes validation row |
| `/bridge/decision/plans/{plan_id}/validations` | GET | Validation history | None |
| `/bridge/decision/plans/{plan_id}/validation/latest` | GET | Latest validation report | None |

**Authority note:** No execute endpoint exists. Approval and validation do not authorize `/bridge/run`.

## System, hardware, bridge (inspection / planning)

| Endpoint | Method | Purpose | Side Effects |
|----------|--------|---------|--------------|
| `/` | GET | Service metadata | None |
| `/flagship` | GET | Flagship program metadata | None |
| `/prefixes` | GET | List Wine prefixes | None |
| `/health` | GET | Health check | None |
| `/metrics` | GET | Prometheus metrics | None |
| `/hardware/profile` | GET | Host hardware and capability profile | None (probes host) |
| `/bridge/inspect` | GET | Compatibility inspection | None (reads target file) |
| `/bridge/program/preflight` | GET | Program readiness check | None |
| `/bridge/installer/preflight` | GET | Installer readiness check | None |
| `/bridge/launcher/preflight` | GET | Launcher readiness check | None |
| `/bridge/plan` | POST | Preview execution strategies | None (no launch) |
| `/bridge/run` | POST | Full adaptive bridge run | **Yes** — launches processes, mutates prefixes, writes outcomes |
| `/bridge/run/async` | POST | Async bridge run | **Yes** — same as run |
| `/bridge/run/{session_id}/result` | GET | Poll async run result | None |
| `/bridge/sessions/recent` | GET | Recent sessions list | None |
| `/bridge/session/{session_id}` | GET | Session attempt history | None |

## Learning, import, training

| Endpoint | Method | Purpose | Side Effects |
|----------|--------|---------|--------------|
| `/outcomes/stats` | GET | Aggregate outcome statistics | None |
| `/outcomes/prior-success` | GET | Prior successful run lookup | None |
| `/import/all` | POST | Import sysdet + resolve history | **Yes** — writes outcomes.db |
| `/import/sysdet` | POST | Import almasysdet history | **Yes** |
| `/import/resolve` | POST | Import alma_resolve audits | **Yes** |
| `/train/ranker/status` | GET | Ranker training status | None |
| `/train/ranker` | POST | Train strategy ranker | **Yes** — writes model artifacts |
| `/datasets/export` | POST | Export training dataset | **Yes** — writes export files |

## Compliance (representative)

| Endpoint | Method | Purpose | Side Effects |
|----------|--------|---------|--------------|
| `/compliance/tls/assess` | POST | TLS posture assessment | Outbound network probe only |
| `/compliance/tls/bridge` | POST | Start TLS modernizing bridge | **Yes** — starts listener process |
| `/compliance/tls/bridges` | GET | List TLS bridges | None |
| `/compliance/tls/bridge/{id}` | DELETE | Stop TLS bridge | **Yes** — stops process |
| `/compliance/drivers` | GET | Device inventory | None (reads sysfs) |
| `/compliance/scan` | POST | Unified compliance report | Outbound probes only |
| `/compliance/autopilot/run` | POST | Diagnose + optional read-only probes | Mutates only if `execute=true` with allow-listed probes |
| `/compliance/autopilot/feedback` | POST | Record pathway feedback | **Yes** — writes healing store |
| `/compliance/program/data` | DELETE | Purge local compliance data | **Yes** — deletes stored data |

## Modernization, automation, operator, container

| Endpoint | Method | Purpose | Side Effects |
|----------|--------|---------|--------------|
| `/modernization/apply` | POST | Apply modernization playbook | **Yes** — host mutations (requires `allow_mutations`) |
| `/automation/run` | POST | Full automation pipeline | **Yes** when `apply=true` (approval token or allow_mutations) |
| `/automation/approve` | POST | Issue approval token | **Yes** — writes token store |
| `/operator/tick` | POST | Operator loop tick | **Yes** — may remediate |
| `/container/run` | POST | Execute container shim pack | **Yes** — launches container |
| `/compatibility/make-work` | POST | Compatibility work session | **Yes** — may launch bridge |

## Auth note

When `ALMA_BRIDGE_API_KEY` is set, mutating endpoints require `X-API-Key` or `Authorization: Bearer`. Default is open on localhost (`SECURITY.md`, `config.py`).

**Sources:** `docs/architecture/API_BOUNDARIES.md`, `alma_bridge/api/routes.py`, `SECURITY.md`.
