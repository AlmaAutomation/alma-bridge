# Runtime Expansion Ranking Test Matrix

ACI Phase 4 tests live in `tests/compatibility_intelligence/expansion/`.
Twenty scenarios validate deterministic, evidence-bound expansion planning.

## Scenarios

| # | Scenario | Assertion |
|---|----------|-----------|
| 1 | Repeated sessions | Distinct binary demand not inflated by duplicate sessions |
| 2 | Capability isolation | App A evidence cannot affect unrelated capability B |
| 3 | Provider isolation | Provider A demand cannot prioritize provider B |
| 4 | Unsupported behavior | Creates bounded behavior-scoped candidate |
| 5 | Stable behavior exclusion | Already-stable behavior excluded from missing-work ranking |
| 6 | Verified bounded limitation | Registry limitation remains visible on candidate |
| 7 | Impact language | Says "blocker removal," not guaranteed success |
| 8 | Complexity deterministic | Same inputs → same complexity score and factors |
| 9 | Risk factors preserved | Security and semantic categories not collapsed |
| 10 | Hard exclusion | Excluded capability cannot rank |
| 11 | Evidence required | No candidate without reproducible evidence |
| 12 | Composite dimensions | All priority dimensions exposed |
| 13 | Unknown APIs | Not guessed into capability mappings |
| 14 | Registry immutable | Plan generation does not mutate registry |
| 15 | No execution | Endpoints do not execute binaries |
| 16 | No provider change | Plan does not alter provider selection |
| 17 | Registry version binding | Old analyses retain their registry version |
| 18 | Plan digest deterministic | Same evidence → same plan digest |
| 19 | file_append_unsupported | Produces append behavior candidate with evidence |
| 20 | Explorer contract | API response exposes scope, demand, impact, risk, evidence distinctly |

## Running tests

```bash
pytest tests/compatibility_intelligence/expansion/ -v
```

Fixtures require native runtime binaries under
`tests/fixtures/native_runtime/bin/` (built separately).

## Language checks

Tests assert response text and summaries use bounded language:

- "observed demand"
- "identified blocker"
- "estimated bounded impact"
- "engineering candidate"
- Absence of "will make compatible" or "guaranteed"
