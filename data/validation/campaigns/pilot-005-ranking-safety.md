# Pilot-005 Ranking Safety for Active Reuse

**Status:** Design policy — not retroactive tuning of Pilot-004 results

## Observation from Pilot-004

`profile_shadow_rank_v1` selected Candidate 2 (`b2a24a3b…`) over Candidate 1 (`a5576257…`) primarily through the **recency** ranking component. The only manifest delta was `WINEDLLOVERRIDES=winemenubuilder.exe=d` — a low-impact configuration difference.

**This does not establish technical superiority.**

## Distinctions

| Concept | Meaning |
|---------|---------|
| Deterministic eligibility | Candidate passes all blocking rejection checks |
| Candidate equivalence | Material manifest fields match (excluding low-impact env keys) |
| Evidence-backed superiority | Outcome history, verification confidence, or failure rate distinguishes candidates |
| Recency-only tie-break | Winner selected solely or primarily by recency with near-equal scores |

## Active Reuse Rules (proposed)

1. **Single eligible candidate** → may be considered for narrow active reuse (`SINGLE_ELIGIBLE_CANDIDATE`)
2. **Multiple equivalent candidates** differing only by low-impact configuration/recency → select only under explicit deterministic equivalence policy (`EQUIVALENT_MANIFEST_TIEBREAK`); **not active-reuse eligible**
3. **Recency-only winner** → shadow observation only; **not active-reuse eligible** (`RECENCY_ONLY_TIEBREAK`)
4. **Material manifest differences** without outcome-history evidence → **not active-reuse eligible** (`INSUFFICIENT_RANKING_EVIDENCE`)
5. **Outcome-history preferred** → may be active-reuse eligible when reuse success rate, verification confidence, or failure penalty clearly distinguish candidates (`OUTCOME_HISTORY_PREFERRED`)

## Persisted Ranking Explanation

Each shadow prediction may include `feature_flags_json.ranking_explanation`:

```json
{
  "profile_id": "...",
  "profile_revision": 4,
  "decisive_components": ["recency"],
  "ranking_reason_code": "RECENCY_ONLY_TIEBREAK",
  "was_tie_break": true,
  "technical_superiority_established": false,
  "active_reuse_eligible": false,
  "notes": "Recency-only tie-break; does not establish technical superiority."
}
```

## Reason Codes

- `SINGLE_ELIGIBLE_CANDIDATE`
- `EQUIVALENT_MANIFEST_TIEBREAK`
- `RECENCY_ONLY_TIEBREAK`
- `OUTCOME_HISTORY_PREFERRED`
- `INSUFFICIENT_RANKING_EVIDENCE`

## Pilot-004 Run J Interpretation Constraint

Run 13 primarily tests deterministic candidate handling and recency-based tie-breaking. It does **not** prove Candidate 2 is more reliable or technically superior.
