# Pilot-005 Campaign Continuity Policy

**Effective:** upon Pilot-005 freeze approval  
**Pilot-004 classification:** `COMPLETED_NOT_PROMOTION_READY`

## Principles

1. **Pilot-005 is a new frozen campaign.** It does not mutate Pilot-004 raw evidence.
2. **Pilot-004 evidence** may contribute to aggregate analysis only through an explicit `ValidationEvidenceScope` after immutable evidence-quality classification.
3. **Product changes** require a new commit, full test suite pass, new campaign freeze, and explicit execution approval.
4. **Active CompatibilityProfile reuse remains DISABLED** until a future campaign explicitly authorizes it.

## Evidence Handling

| Action | Allowed |
|--------|---------|
| Read Pilot-004 completion report | Yes |
| Scope Pilot-004 runs into campaign-scoped gates | Yes, via `ValidationEvidenceScope` |
| Relabel or rewrite Pilot-004 raw records | **No** |
| Mix post-fix Pilot-005 runs into Pilot-004 evidence | **No** |
| Use Pilot-004 Run 9 in promotion gates | **No** (exploratory_only) |

## Freeze Requirements

Before Pilot-005 execution approval:

- Corrective engineering commit merged
- Full authoritative test suite: zero failures
- New source snapshots or verified hash continuity documented
- API-compatible known-failure precondition proven
- Semantic validator and freeze validator pass
- Campaign manifest status: `ready_for_execution_approval`

## Stop Conditions

Same as Pilot-004, plus:

- Evidence persistence failure without `EVIDENCE_PERSISTENCE_INCOMPLETE` classification
- Campaign-scoped gate computation including historical pollution
- Active reuse enabled during campaign

## Active Reuse

**Not authorized** by Pilot-004 completion or Pilot-005 preparation.
