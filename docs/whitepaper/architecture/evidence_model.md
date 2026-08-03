# Evidence Model — Architecture Deep-Dive

**Status:** As-built (ADR-002, DATA_FLOW)  
**Companion:** [evidence_flow.mmd](../diagrams/evidence_flow.mmd), [data_model_overview.mmd](../diagrams/data_model_overview.mmd)

## Authoritative store

`storage/outcomes.py` owns `data/outcomes.db` (path from `settings.db_path`):

### `bridge_sessions`

Primary session record: `session_id`, `file_path`, `file_hash`, timestamps, `success`, `hardware_profile`, `summary`, lifecycle fields (`session_state`, `parent_session_id`, `correlation_id`), JSON columns (`inspection_json`, `policy_context_json`, `escalation_json`, `run_environment_json`), lease columns.

### `bridge_attempts`

Per-attempt record: `strategy_id`, `runtime`, `command`, `env`, `success`, `exit_code`, `error_signature`, stdout/stderr, `verification_json`, `phase`, `policy_decision_json`, etc.

**Write authority stops here** for the compatibility evidence chain. Platform tier opens the same file for SELECT-only access via adapters.

## EvidenceBundleBuilder

`intelligence/evidence.py::EvidenceBundleBuilder` is the shared read-path primitive:

**Inputs:** Session records via `CompatibilityEvidenceRepository` / `OutcomesStoreAdapter`, plus profile and shadow reads where available.

**Outputs:**

- `references`: list of `EvidenceReference` with `EvidenceSourceType` enum (SESSION, INSPECTION, ATTEMPT, VERIFICATION, FRAMEWORK_DETECTION, MANIFEST_CAPTURE, SHADOW_COMPARISON, RUN_ENVIRONMENT, …).
- `artifacts`: keyed payloads e.g. `attempt:{session_id}:{n}`, `verification:{session_id}:{n}`, `run_environment:{session_id}`.
- `limitations`: explicit gaps (missing manifest, pre-v2 capture, etc.).

## Fact vs hypothesis (intelligence layer)

| Output type | Meaning | Authority |
|-------------|---------|-----------|
| CompatibilityFact | Proven claim with evidence refs | Requires authoritative verification for success facts |
| CompatibilityHypothesis | Unresolved or shadow-derived | Never promoted without verification pass |

Shadow predictions are evidence inputs only (ADR-002 §3).

## Downstream reshaping

| Consumer | Transform |
|----------|-----------|
| `graph/ingestion.py` | Materialize nodes/edges with `GraphProvenance` |
| `knowledge/aggregation.py` | `CompatibilityKnowledgeProfile` with `evidence_by_field` |
| `regression/diff.py` | Baseline vs current profile diff |
| `comparison/queries.py` | `SessionEvidenceSnapshot` for pair compare |
| `catalog/aggregation.py` | Catalog row per fingerprint |

## Provenance models

Two reference types exist: `intelligence.models.EvidenceReference` and `knowledge.models.KnowledgeEvidenceReference`. `comparison/queries.py` bridges via private `_to_knowledge_ref` (TD4 — encapsulation debt).

## Application identity limitation

Cross-session queries use `file_hash` equality (`list_sessions_for_fingerprint`). This is not a full program-identity graph key (ADR-002 consequences, R8).

## Technical debt (evidence path)

- Framework heuristics duplicated in `intelligence/evidence.py` vs `compatibility/framework_detection.py` (TD3).
- Read adapters use `outcomes._connect()` private API (TD5).
- Six near-identical NotFound error types across read-only packages (TD1).

## Related documents

- [DATA_FLOW.md](../../architecture/DATA_FLOW.md) §2–§5
- [ADR-002](../../adr/ADR-002-compatibility-intelligence-boundary.md)
- [ADR-008](../../adr/ADR-008-compatibility-run-environment-catalog.md)
