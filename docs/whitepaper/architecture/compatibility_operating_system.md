# Alma Compatibility Operating System

**Status:** As-built (Alma v2.0 evidence integration)  
**Companion:** [evidence_flow.mmd](../diagrams/evidence_flow.mmd), [evidence_lifecycle.mmd](../diagrams/evidence_lifecycle.mmd)

## Thesis

Alma is a **deterministic compatibility operating system driven by evidence**. Every subsystem — static analysis, prediction, execution, verification, knowledge, regression, decision, governance, and expansion planning — contributes to one continuous, append-only evidence lifecycle. Nothing overwrites history; every stage consumes prior evidence and appends new evidence with provenance.

## Core pipeline

```
Executable → Static Analysis → Capability Intelligence → Coverage → Prediction
  → Runtime Selection → Execution Provider → Verification → Knowledge
  → Regression → Decision → Review → Validation → Governance
  → Runtime Expansion Planning → Historical Evidence
```

Each arrow is an evidence-producing stage. Downstream consumers read references and digests; they do not mutate upstream artifacts.

## CompatibilityEvidenceBundle

The bundle is the single read model for an executable's complete compatibility story:

| Section | Source subsystem | Mutability |
|---------|------------------|------------|
| Executable (binary digest) | PE analyzer / outcomes | Immutable |
| Static analysis | ACI analyzer | Immutable |
| Capability graph | ACI graph builder | Immutable |
| Coverage | ACI coverage engine | Immutable |
| Prediction + snapshot | ACI predictor + calibration | Immutable |
| Execution metadata + runtime provider | Runtime providers / orchestrator | Immutable |
| Verification report | VerificationEngine | Authoritative |
| Knowledge summary | Knowledge aggregation | Append-only |
| Regression summary | Regression diff | Append-only |
| Advisor observations | Advisor service | Append-only |
| Decision plan | Decision Engine | Immutable per version |
| Review | Decision Review | Immutable per review |
| Validation | Decision Validation (dry-run) | Immutable per report |
| Governance state | ACI Governance | Append-only registry versions |
| Expansion recommendations | ACI Expansion | Immutable per plan |
| Historical versions | Evidence history | Append-only |

## Timeline events

Immutable lifecycle events bind stages together:

- `AnalysisCreated`, `PredictionGenerated`, `ExecutionStarted`, `VerificationCompleted`
- `KnowledgeUpdated`, `RegressionDetected`, `DecisionGenerated`
- `ReviewApproved`, `ValidationCompleted`, `GovernanceApplied`, `ExpansionCandidateGenerated`

Each event carries: timestamp, version, evidence digest, schema version, source, references.

## Authority boundaries (unchanged)

| Component | Authority |
|-----------|-----------|
| VerificationEngine | Success/failure verdict |
| Runtime providers | Execution only |
| Governance apply | Registry mutation (human-gated) |
| Decision Validation | Dry-run only — no execution |
| Evidence service | Append-only storage — no inference |

## Platform health

Evidence-backed metrics with sample sizes:

- Native runtime coverage, behavior coverage
- Prediction precision/recall, calibration accuracy
- Verification rate, governance proposals, expansion backlog
- Runtime maturity, capability maturity, unknown APIs, behavior gaps

## Integration principle

**Integrate, do not duplicate.** The `alma_bridge/evidence/` package aggregates from existing repositories (`AnalysisRepository`, `CalibrationRepository`, `GovernanceRepository`, `ExpansionPlanRepository`, intelligence evidence builder, decision services). Subsystems append timeline events; the evidence service never replaces subsystem logic.

## Related documents

- [evidence_model.md](./evidence_model.md) — authoritative store and read paths
- [decision_pipeline.md](./decision_pipeline.md) — plan → review → validate
- [verification_authority.md](./verification_authority.md) — verification law
- [read_only_intelligence.md](./read_only_intelligence.md) — intelligence boundary
