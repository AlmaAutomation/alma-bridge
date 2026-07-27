# ADR-002: Compatibility Intelligence Boundary

## Status

Accepted — 2026-07-27

## Context

Alma Bridge produces rich execution evidence — session records, attempt verification JSON,
framework detection artifacts, manifest capture, and shadow comparison metrics. Downstream
platform surfaces (Explorer, AI Advisor, Knowledge Database ingestion) need a **deterministic,
read-only** layer that turns raw persistence into structured compatibility assessments without
re-entering the execution authority boundary established by [ADR-001](ADR-001-authoritative-bridge-lifecycle.md).

Prior to this decision, no single subsystem owned the translation from persisted evidence to
labeled facts and hypotheses. Operators risked conflating proxy signals (exit codes, shadow
predictions, stderr heuristics) with verified compatibility outcomes.

## Decision

Introduce **Compatibility Intelligence** as a read-only platform capability under
`alma_bridge/intelligence/`. It consumes persisted evidence through a repository adapter,
builds versioned `EvidenceBundle` artifacts, and emits deterministic `CompatibilityAssessment`
results via `CompatibilityAssessmentEngine` (`engine_version = compatibility_intelligence_v1`).

### 1. Read-only platform layer — never execution authority

Compatibility Intelligence **reads** evidence and **assesses** compatibility claims. It never
launches processes, mutates prefixes, emits `ActionIntent`, invokes the orchestrator, or calls
`VerificationGateway`. Assessment output informs operators and future platform surfaces only.

### 2. Facts require evidence; hypotheses are separate

Every `CompatibilityFact` must cite one or more `EvidenceReference` records with a validated
`source_type`. Unresolved questions, runtime guesses, and shadow predictions are modeled as
`CompatibilityHypothesis` — never promoted to facts without authoritative verification evidence.

### 3. Shadow predictions are not proven facts

Shadow profile predictions and comparison metrics may appear in evidence bundles as inputs to
hypotheses or limitations. They **must not** be recorded as proven compatibility facts or
used to imply verified launch success.

### 4. Verified success only from aggregate verification pass

`verified_successful_launch` is proven **only** when the winning attempt's persisted
`VerificationResult` has `passed=True` under its versioned aggregate success policy.
Subprocess `exit_code == 0`, route-level success, attempt `success=1` without verification
pass, and session summary strings are **not** sufficient alone.

### 5. Prohibited dependencies

The intelligence package must not import:

- `alma_bridge.learning.orchestrator`
- `alma_bridge.session.verification_gateway`
- `alma_bridge.session.mutations` (prefix mutation)
- winetricks or runtime installer modules
- LLM or advisory inference loops

Assessment logic may read persisted verification JSON structurally; it does not re-invoke
`VerificationEngine`.

### 6. Deterministic assessment only

Given the same evidence bundle input, `CompatibilityAssessmentEngine` produces identical
facts, hypotheses, confidence summaries, and stable sort order. No ML, randomness, or
network calls in the assessment path.

### 7. Repository isolates persistence from the engine

`CompatibilityEvidenceRepository` (Protocol) and `OutcomesStoreAdapter` own all database reads.
The assessment engine receives in-memory evidence structures only — no direct SQL.

### 8. Read-only HTTP API

Expose assessment results via:

- `GET /bridge/intelligence/sessions/{session_id}`
- `GET /bridge/intelligence/applications/{fingerprint}`

Return `404` when no evidence exists. Return structured validation errors for malformed
evidence references. No mutating endpoints.

## Consequences

### Positive

- Single deterministic layer for fact vs hypothesis labeling
- Safe consumption path for Explorer and AI Advisor without execution coupling
- Architecture tests enforce boundary invariants permanently
- Code::Blocks and future verified apps produce reproducible intelligence assessments

### Negative

- Framework detection in bundles depends on persisted artifacts (re-detection is out of scope)
- Application fingerprint queries use `file_hash` correlation until unified graph ingestion
- Manifest capture completeness varies for pre-`manifest_capture_v2` sessions

## Related artifacts

- `alma_bridge/intelligence/`
- `tests/intelligence/`
- [Platform direction — Compatibility Intelligence Phase 1](../architecture/alma-bridge-platform-direction.md)
- [ADR-001: Authoritative Bridge Lifecycle](ADR-001-authoritative-bridge-lifecycle.md)
