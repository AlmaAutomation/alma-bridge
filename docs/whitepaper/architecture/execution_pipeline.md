# Execution Pipeline — Architecture Deep-Dive

**Status:** As-built documentation (Phase 1 audit, 2026-07-31)  
**Companion:** [execution_pipeline.mmd](../diagrams/execution_pipeline.mmd)

## Vertical chain mapping

The operator-facing pipeline emphasizes nine stages. The table maps each stage to repository modules and notes external dependencies.

| Stage | Module(s) | In-repo? | Writes evidence? |
|-------|-----------|:--------:|:----------------:|
| Alma Automation | `automation/runner.py`, `automation/playbooks.py`, `automation/verify.py` | Yes | Automation audit SQLite; optional `POST /bridge/run` |
| Binary Compatibility Scanner | **External:** `almasysdet`. **Bridge:** `bridge/profile_builder.py`, `GET /bridge/inspect`, `importers/sysdet.py` | Partial | Import writes `outcomes.db`; inspect is read-only |
| Execution Verification | `session/services/verification.py`, `session/verification_gateway.py`, `session/stop_on_success_verification.py` | Yes | Writes `verification_json`, session success |
| Compatibility Graph | `graph/ingestion.py`, `graph/service.py` | Yes | Graph tables on ingestion only |
| Knowledge Aggregation | `knowledge/aggregation.py`, `knowledge/service.py` | Yes | No (computed on read) |
| Regression Intelligence | `regression/diff.py`, `regression/service.py` | Yes | No |
| Environment Comparison | `comparison/diff.py`, `comparison/service.py` | Yes | No |
| Advisor | `advisor/explanation.py`, `advisor/service.py` | Yes | No |
| Ask Alma | `ask/service.py`, `ask/answer.py` | Yes | No |

**Evidence substrate:** `intelligence/EvidenceBundleBuilder` sits between verification persistence and all read-only stages (ADR-002).

## Core write path: `/bridge/run`

1. **Request validation** — `validation/campaign_guard.py` may reject campaign-prefix requests with HTTP 403.
2. **Orchestration** — `BridgeOrchestrator.run()` in `learning/orchestrator.py` acquires session lease, selects strategies via planner + optional ranker.
3. **Execution** — `execution/runner.py` launches Wine/Proton/Electron/container per strategy.
4. **Verification boundary** — `VerificationGateway.run()` transitions to `VERIFYING`, invokes `DefaultVerificationEngine.verify_execution()`.
5. **Success declaration** — Only `declare_verified_session_success()` may set `SUCCEEDED` and `finalize_session(success=True)`.
6. **Persistence** — `storage/outcomes.py` records session and attempts including `verification_json`, `inspection_json`, `run_environment_json` (ADR-008).

## Alma Automation spine

`automation/runner.py` implements:

```
scan → assess → playbook → apply → verify → bridge → autopilot → learn
```

Key behaviors documented in source:

- Default is plan-only (`apply=false`); mutations require `allow_mutations` or valid approval token from `automation/approval.py`.
- Post-apply verification calls `automation/verify.py` → `verify_modernization`.
- Optional `bridge_run` delegates to `BridgeOrchestrator` with constrained `max_attempts`.
- Sessions persisted via `automation/sessions.py` (separate from bridge session tables).

## Binary scanning boundary

**almasysdet** (separate repository) performs static binary analysis and maintains `alma.db`. Alma Bridge:

- Imports historical runs via `POST /import/sysdet` → `importers/sysdet.py`.
- Performs local inspection via `build_compatibility_inspection()` without requiring almasysdet at runtime for `/bridge/inspect`.

Bridge does **not** embed the full almasysdet scanner; the white paper treats "Binary Compatibility Scanner" as a **two-part** capability: external scanner + bridge inspection/import.

## Read path activation

Read-only stages activate on HTTP GET (or Ask POST) and never call back into the orchestrator. Data flow:

```
outcomes.db → OutcomesStoreAdapter → EvidenceBundleBuilder → {graph,knowledge,regression,comparison,catalog} → advisor → ask
```

## Illustrative code references

Verification gateway eligibility check pattern:

```python
# alma_bridge/session/verification_gateway.py — OBSERVING → VERIFYING transition
# Only after DefaultVerificationEngine returns structured result
```

Orchestrator as sole lifecycle owner (ADR-001):

```python
# alma_bridge/learning/orchestrator.py — BridgeOrchestrator.run()
# Invoked from POST /bridge/run in api/routes.py
```

## Tests

- `tests/test_verification_authority.py` — success path exclusivity
- `tests/test_orchestrator_authority.py` — orchestrator lifecycle ownership
- `tests/automation/` — automation spine (where present)
- Package boundary tests for read-only tiers

## Related documents

- [DATA_FLOW.md](../../architecture/DATA_FLOW.md)
- [ADR-001](../../adr/ADR-001-authoritative-bridge-lifecycle.md)
- [limitations.md](../appendices/limitations.md)
