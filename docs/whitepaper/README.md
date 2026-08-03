# Alma Bridge Technical White Paper — Package Index

**Version:** Alma v2.0 Compatibility Operating System (as-built 2026-08-02)  
**Audience:** Systems architects, platform engineers, security reviewers

## Alma v2.0 thesis

Alma is a **deterministic compatibility operating system driven by evidence**. One executable tells a complete story through an immutable `CompatibilityEvidenceBundle` and lifecycle timeline. Subsystems integrate into the evidence pipeline; they do not form independent silos.

## Source-of-truth note

This white paper describes **what is implemented and tested** in the `alma-bridge` repository as of the Phase 1 architecture audit (2026-07-31). When this document disagrees with marketing language or informal README phrasing, the following sources prevail in order:

1. Implemented code under `alma_bridge/` and `tests/`
2. Accepted ADRs in `docs/adr/`
3. Phase 1 audit documents in `docs/architecture/`
4. This white paper package

Items labeled **Future work** are documented intent without implementation evidence.

## How to read

| Reader goal | Start here |
|-------------|------------|
| Executive overview | [alma_bridge_whitepaper.md](./alma_bridge_whitepaper.md) §1–§6 |
| Execution and verification law | §7–§8; [architecture/verification_authority.md](./architecture/verification_authority.md) |
| Evidence lifecycle and operating system | §9–§15; [architecture/compatibility_operating_system.md](./architecture/compatibility_operating_system.md), [architecture/evidence_model.md](./architecture/evidence_model.md) |
| Evidence and read-only platform | [architecture/read_only_intelligence.md](./architecture/read_only_intelligence.md) |
| Decision pipeline (plan → review → validate) | §16; [architecture/decision_pipeline.md](./architecture/decision_pipeline.md) |
| API surface | [tables/api_endpoints.md](./tables/api_endpoints.md); white paper §17–§18 |
| Security deployment | §19; [architecture/security_model.md](./architecture/security_model.md) |
| Honest gaps | §23; [appendices/limitations.md](./appendices/limitations.md) |
| Document quality audit | [appendices/self_review.md](./appendices/self_review.md) |

## Package contents

```
docs/whitepaper/
├── README.md                          ← this file
├── alma_bridge_whitepaper.md          ← main document (~24 sections)
├── bibliography.md                    ← references
├── architecture/
│   ├── execution_pipeline.md
│   ├── verification_authority.md
│   ├── compatibility_operating_system.md  ← Alma v2.0 evidence lifecycle
│   ├── evidence_model.md
│   ├── read_only_intelligence.md
│   ├── decision_pipeline.md           ← Decision Engine Phases 1–3
│   └── security_model.md
├── diagrams/
│   ├── overall_architecture.mmd
│   ├── decision_pipeline.mmd          ← plan → review → validate
│   ├── execution_pipeline.mmd
│   ├── verification_authority.mmd
│   ├── evidence_flow.mmd
│   ├── evidence_lifecycle.mmd             ← unified pipeline
│   ├── layer_diagram.mmd
│   ├── dependency_boundaries.mmd
│   ├── data_model_overview.mmd
│   └── plugin_architecture_proposal.mmd  ← Future work / design-only
├── tables/
│   ├── subsystems.md
│   ├── api_endpoints.md
│   └── adrs.md
└── appendices/
    ├── terminology.md
    ├── limitations.md
    └── self_review.md
```

## Diagram rendering

Mermaid sources in `diagrams/` are embedded in the main white paper where appropriate. Render with any Mermaid-compatible viewer (GitHub, VS Code extension, or `mmdc` CLI).

## Related repository documentation

- [docs/architecture/SYSTEM_OVERVIEW.md](../architecture/SYSTEM_OVERVIEW.md) — Phase 1 audit entry point
- [docs/adr/](../adr/) — architecture decisions
- [SECURITY.md](../../SECURITY.md) — deployment security

## Maintenance

Update this package when:

- New ADRs are accepted (extend `tables/adrs.md` and §17)
- Boundary tests or module structure change (refresh diagrams and subsystem table)
- Benchmarks become available (§19)
- Plugin Phase 8 implementation begins (relabel from Future work)

Run self-review checklist in [appendices/self_review.md](./appendices/self_review.md) after substantive edits.
