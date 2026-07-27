# Pilot-005 Corrective Engineering Package

**Status:** PREPARED — NOT APPROVED FOR EXECUTION  
**Pilot-004 classification:** `COMPLETED_NOT_PROMOTION_READY`  
**Active reuse:** **DISABLED**

---

## 1. Pilot-004 Final Classification

| Field | Value |
|-------|-------|
| Campaign | `shadow-validation-pilot-004` |
| Terminal status | `completed` |
| Promotion classification | `COMPLETED_NOT_PROMOTION_READY` |
| Freeze commit | `6261d47ce5a2060571de45a1ab33f8163b3de776` |
| Evidence preserved | `data/validation/evidence/pilot-004/` |

---

## 2. Evidence Quality Review

Immutable review: `data/validation/campaigns/pilot-004-evidence-quality-review.json`

| Classification | Runs |
|----------------|------|
| `promotion_eligible_evidence` | 1–8, 10–13 (12 runs) |
| `exploratory_only` | 9 (direct orchestrator bypass; excluded from gates) |

Raw records were not rewritten.

---

## 3. Corrected Campaign-Scoped Metrics

Command:

```bash
alma-bridge-shadow-validation gates --campaign-id shadow-validation-pilot-004
```

Artifact: `data/validation/evidence/pilot-004/scoped-gates.json`

| Gate | Numerator | Denominator | Passed |
|------|-----------|-------------|--------|
| min_comparisons | 9 | 9 | ✗ (req 50) |
| min_drift_scenarios | 2 | 2 | ✗ (req 10) |
| min_rejection_scenarios | 4 | 4 | ✗ (req 10) |
| min_program_kinds | 3 | 3 | ✓ |
| eligibility_precision | 9 | 9 (100%) | ✓ |
| false_eligibility_rate | 0 | 9 | ✓ |
| drift_false_positive_rate | 0 | 6 | ✓ |
| rank_agreement | 8 | 8 | ✓ |
| no_duplicate_profile_defects | 8 | 9 | ✗ |

**Historical pollution removed:** unscoped duplicate rate was 0.6452 (31 global comparisons); scoped rate is 8/9 from campaign execution lineage (promoted profile ≠ predicted winner), not Pilot-001/002/003 history.

**Excluded from scope:** Pilot-001/002/003, Run 9 exploratory session, legacy WINEPREFIX identity-leak profiles, controlled duplicate fixture B.

Every gate check persists `numerator`, `denominator`, and `included_ids`.

---

## 4. Manifest Completeness — Root Cause & Fix

### Root cause (Run 7)

`ProfileCandidateService.persist_from_verified()` did not capture prefix state. Stored profiles had `installed_components: []` while drift used effective prefix observation.

### Fix

- `alma_bridge/compatibility/profile_manifest_capture.py` — `capture_verified_manifest_context()`
- Wired into `ProfileCandidateService.build_snapshot()` at verification time
- Manifest fields: `manifest_capture_version: manifest_capture_v2`, `component_capture_complete: true`
- `manifest_reconstruction_eligible()` rejects incomplete legacy manifests
- `MANIFEST_CAPTURE_INCOMPLETE` reason code for audit (non-blocking for shadow observation)

---

## 5. API-Compatible Known-Failure Replacement (Run G)

**Pilot-004 Run 9:** exploratory only (executable deletion + API 404).

**Pilot-005 approach:** remove `ntdll.dll` from disposable prefix while keeping `notepad.exe` present.

Dry-run proof: `scripts/validation/pilot005_known_failure_precondition.py`

Preserves: file existence, canonical identity, `/bridge/run` API path, bounded failure, immutable shadow records. **No product bypass.**

---

## 6. Evidence Persistence Fix

`alma_bridge/validation/campaign_evidence.py`

- `prepare_run_evidence_paths()` — directories before execution
- `persist_run_evidence()` — atomic write with metadata
- `EVIDENCE_PERSISTENCE_INCOMPLETE` on failure
- `recover_run_evidence_from_db()` — DB recovery without re-execution

Root cause: Run 10 wrote `response.json` before `run-10/` existed.

---

## 7. Ranking Safety Design

Document: `data/validation/campaigns/pilot-005-ranking-safety.md`

- Ranking explanations persisted in `feature_flags_json.ranking_explanation`
- Reason codes: `SINGLE_ELIGIBLE_CANDIDATE`, `EQUIVALENT_MANIFEST_TIEBREAK`, `RECENCY_ONLY_TIEBREAK`, `OUTCOME_HISTORY_PREFERRED`, `INSUFFICIENT_RANKING_EVIDENCE`
- Recency-only winners are **not** active-reuse eligible

---

## 8. Pilot-005 Additional Run Allocation

Scoped shortfall → additional runs required:

| Gate | Current (scoped) | Target | Gap |
|------|----------------|--------|-----|
| Labelable comparisons | 9 | 50 | ~41 |
| Drift scenarios | 2 | 10 | ~8 |
| Rejection scenarios | 4 | 10 | ~6 |

**Proposed 48-run matrix** with diversity across T1 native, T2/T3/32-bit, host overlays, drift, trust, API known-failure, multi-candidate ranking. Not repeating identical Notepad-only runs.

---

## 9. Campaign Continuity

`data/validation/campaigns/pilot-005-continuity-policy.md`

---

## 10. Feature Flags (unchanged)

```
ALMA_BRIDGE_COMPATIBILITY_PROFILE_REUSE_ENABLED=false
```

All other Pilot-004 flags unchanged. Active reuse **prohibited**.

---

## 11. Tests

`tests/test_pilot005_corrective.py` — 17 tests covering scoped metrics, manifest capture, evidence persistence, ranking safety, evidence quality review.

Focused validation tests: 37 passed.

Full suite: 14 pre-existing failures in `test_verification_authority` / `test_wine_gui_contract` (present on freeze commit `6261d47`; not introduced by corrective engineering).

---

## 12. Freeze Plan (Pilot-005)

1. Commit corrective engineering
2. Full suite on clean DB (address pre-existing failures separately)
3. Create `shadow-validation-pilot-005.json`
4. Source snapshots / hash continuity
5. API known-failure dry-run proof
6. Semantic + freeze validators
7. Approval package → `ready_for_execution_approval`
8. **Await explicit execution approval**

---

## 13. Confirmation

**Active CompatibilityProfile reuse remains DISABLED.**  
**Pilot-005 is prepared but NOT executed.**
