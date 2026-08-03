# Runtime Expansion Planning Architecture

ACI Phase 4 produces **advisory engineering plans** for NativeAlmaRuntime
expansion. Plans rank narrowly scoped implementation candidates from
observed compatibility evidence.

## Boundary

| Allowed | Forbidden |
|---------|-----------|
| Read PE analyses, calibration, governance registry | Mutate capability registry |
| Aggregate deduplicated demand counts | Auto-implement Win32 APIs |
| Rank bounded engineering candidates | Promote capabilities |
| Persist generated plans (read-only generation) | Execute binaries |
| Expose GET API endpoints | Change provider selection |
| Link to evidence references | Generate or apply code patches |
| | Use LLM to choose priorities |

## Package layout

```
alma_bridge/compatibility_intelligence/expansion/
├── models.py       # RuntimeExpansionCandidate, RuntimeExpansionPlan
├── demand.py       # Deterministic demand aggregation
├── impact.py       # Bounded impact estimates
├── complexity.py   # Engineering complexity with factors
├── risk.py         # Security + semantic risk categories
├── ranking.py      # Deterministic priority ranking
├── repository.py   # Plan persistence
├── service.py      # Orchestration
├── digest.py       # Plan/candidate digests
└── errors.py
```

## Evidence inputs (consume only)

- PE analyses and unknown/unsupported APIs
- Behavioral profiles and unsupported behaviors
- Calibration false positives and provider eligibility blockers
- Application/session counts (deduplicated by binary digest)
- Verification history and Wine successes
- Registry maturity, limitations, security classifications

Demand is **not** inferred from popularity without explicit Alma usage evidence.

## Candidate model

Each candidate includes:

- Scoped identity: `provider_id`, `capability_id`, optional `behavior_id`
- DLL/API symbols and bounded `implementation_scope`
- `affected_application_fingerprints`, `affected_analysis_digests`
- Raw demand counts and normalized `demand_score`
- `BoundedImpactEstimate` with blocker-removal language
- `ComplexityAssessment`, `SecurityRiskAssessment`, `SemanticRiskAssessment`
- `testability`, `evidence_quality`, `priority` dimensions
- `limitations`, `evidence_references` (registry limitations retained)

## Demand deduplication

Sessions sharing a binary digest count once toward distinct binary demand.
Application fingerprints are tracked separately. Provider A demand never
prioritizes provider B candidates.

## Impact language

Use precise phrasing:

- **Observed demand** — deduplicated evidence counts
- **Identified blocker** — static/calibration gap blocking eligibility
- **Estimated bounded impact** — could remove blocker for N analyses
- **Engineering candidate** — not a compatibility guarantee

## Hard exclusions

Candidates matching these patterns are excluded from ranking:

- Kernel driver implementation
- Anti-cheat surfaces
- Arbitrary DLL loading
- Unbounded process creation
- Undocumented scope without reproducible test fixture

## API

| Endpoint | Purpose |
|----------|---------|
| `GET /bridge/compatibility/expansion/plan` | Full ranked plan (filters optional) |
| `GET /bridge/compatibility/expansion/candidates/{id}` | Single candidate detail |
| `GET /bridge/compatibility/expansion/capabilities/{capability_id}` | Candidates for capability |

## Acceptance: file_append_unsupported

The fixture `file_append_unsupported.exe` must produce a bounded candidate for
`filesystem.basic_io / append_existing_file`:

- Symbol support present; behavioral gap reported
- Links to fixture evidence
- Impact states likely blocker removal, not guaranteed compatibility
- Registry limitation retained; maturity not mutated

`console.stdout` must not rank as missing work when already `verified_bounded`
for supported behaviors.

Unknown APIs become separate candidates only when classification confidence
is explicit — no guessed capability mapping.
