# Alma Bridge Technical White Paper — Package Index

**Version:** Phase 1 as-built (audit date 2026-07-31)  
**Audience:** Systems architects, platform engineers, security reviewers

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
| Evidence and read-only platform | §9–§15; [architecture/evidence_model.md](./architecture/evidence_model.md), [architecture/read_only_intelligence.md](./architecture/read_only_intelligence.md) |
| API surface | [tables/api_endpoints.md](./tables/api_endpoints.md); white paper §16–§17 |
| Security deployment | §18; [architecture/security_model.md](./architecture/security_model.md) |
| Honest gaps | §22; [appendices/limitations.md](./appendices/limitations.md) |
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
│   ├── evidence_model.md
│   ├── read_only_intelligence.md
│   └── security_model.md
├── diagrams/
│   ├── overall_architecture.mmd
│   ├── execution_pipeline.mmd
│   ├── verification_authority.mmd
│   ├── evidence_flow.mmd
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
