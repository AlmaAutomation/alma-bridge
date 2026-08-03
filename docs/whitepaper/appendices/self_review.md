# White Paper Self-Review

**Review date:** 2026-07-31  
**Documents reviewed:** `docs/whitepaper/alma_bridge_whitepaper.md` and supporting files in this package.

## Method

Each major claim in the main white paper was checked against: implemented code under `alma_bridge/`, tests under `tests/`, ADRs in `docs/adr/`, and Phase 1 architecture audit documents in `docs/architecture/`. Items without direct evidence were labeled **Future work** or removed.

## Unsupported claims flagged and resolved

| Claim (draft risk) | Resolution |
|--------------------|------------|
| "Compatibility Explorer UI in alma-bridge" | Corrected: no frontend package in repo; external HTTP UIs only (`SYSTEM_OVERVIEW` §2) |
| "Plugins are supported" | Labeled **Future work** throughout; cites `plugin-architecture.md` stub |
| "ML drives execution decisions" | Scoped: ranker scores strategies during planning; assessment/regression/advisor paths are deterministic per ADRs |
| "Graph influences planner" | Explicitly denied per ADR-003; graph is non-authoritative |
| "POST /bridge/ask mutates state" | Documented as read-only POST (no persistence) per ADR-007 and boundary tests |
| "Unified database layer" | Not claimed; limitation documented (R1) |
| End-to-end performance SLAs | Not stated; compliance concurrency only where README documents measurements |

## Missing citations added

- Vertical pipeline chain mapped to concrete modules with external vs in-repo labels for Alma Automation and Binary Scanner.
- Verification authority chain cites `verification_gateway.py`, ADR-001, `test_verification_authority.py`.
- Evidence model cites `EvidenceBundleBuilder` and `DATA_FLOW.md` §4.
- Security section cites `SECURITY.md`, `api/auth.py`, campaign guard.

## Duplication notes

- Layer diagram appears in main doc (embedded mermaid), `diagrams/layer_diagram.mmd`, and `architecture/` deep-dives — intentional: main doc for narrative, `.mmd` for reuse, deep-dives for detail.
- Subsystems table duplicated inline in §6 and `tables/subsystems.md` — intentional for standalone table export.
- ADR summaries appear in §17 and `tables/adrs.md`.

## Terminology inconsistencies corrected

| Issue | Fix |
|-------|-----|
| "Environment Comparison" vs package name `comparison/` | Both used with explicit ADR-009 title "Environment-Aware Session Comparison" |
| "Execution Verification" vs "Verification" layer | Mapped to `session/services/verification.py` + gateway; distinguished from compliance verify-after-apply in automation |
| "Knowledge Database" vs `knowledge/` package | Phase 1 aggregation is computed on read; "database" wording avoided for persistence that does not exist |

## Clarity improvements applied

1. Executive summary states audit date and evidence basis.
2. Timeline diagram distinguishes **external** almasysdet from **in-repo** inspection.
3. Performance section separates documented compliance measurements from "not yet benchmarked" bridge path.
4. Optional LLM paths in advisor/ask clearly marked as configuration-dependent (`settings.advisor_llm_enabled`).
5. Catalog described as top-level browser (ADR-008), parallel to chain not after Ask Alma.

## Residual gaps (thin implementation evidence)

| Topic | Gap | How white paper handles it |
|-------|-----|----------------------------|
| Operator loop production usage | Optional lifespan feature; limited dedicated docs | Described as optional background core component |
| ML ranker accuracy metrics | Training exists; no published accuracy benchmarks | Described as HistGradientBoostingClassifier without performance claims |
| Shadow validation campaigns | Extensive modules; campaign semantics spread across compatibility/ | Summarized with CLI and gate endpoints; detail in compatibility profile docs |
| Cloud sync / Explorer UI | Platform direction only | **Future work** |
| SOC 2 / certifications | SECURITY.md states "Not yet" | Quoted accurately |

## Reviewer checklist

- [x] No marketing superlatives without test/ADR backing
- [x] Every pipeline stage mapped to module path
- [x] Read-only boundary stated with test enforcement reference
- [x] Limitations appendix cross-linked from §22
- [x] Plugin section labeled design-only
- [x] Bibliography lists all cited internal docs

## Recommended follow-up (documentation, not code)

1. Add benchmark harness results to §19 when available.
2. Relocate verification predicate to neutral module and update boundary diagrams (Phase 3 work plan).
3. Expand self-review when ADR-010+ ship or frontend lands in a sibling repo.
