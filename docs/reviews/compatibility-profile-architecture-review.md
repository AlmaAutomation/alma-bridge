# Compatibility Profile Architecture Review

**Date:** 2026-07-14  
**Scope:** `alma_bridge/compatibility/`, orchestrator integration, shadow validation, campaign infrastructure  
**Status:** Review only — no production code modified  
**Context:** Post Pilot-004 (`COMPLETED_NOT_PROMOTION_READY`); Pilot-005 corrective engineering prepared, not executed  
**Active reuse:** **DISABLED** (`compatibility_profile_reuse_enabled=false`)

---

## Executive Summary

Alma Bridge's CompatibilityProfile subsystem is a **shadow-mode learning layer** that captures verified bridge configurations, stores them as immutable versioned profiles, and — without influencing execution — predicts which stored profile would have been reused and scores that prediction against actual outcomes. Active reuse remains explicitly prohibited behind a quantitative promotion-gate process.

The architecture is unusually disciplined for a pilot-stage feature: layered content-addressed identity, observe-only shadow mode, append-only evidence, verification binding, and failure isolation on the hot path. Pilot-004 validated core safety properties (host-overlay rejection, drift detection, trust/invalidation exclusion, deterministic ranking) but did not meet promotion volume thresholds. Pilot-005 corrective work addresses manifest capture, campaign-scoped gate hygiene, ranking-safety classification, and evidence persistence — without authorizing reuse.

**Bottom line:** The foundation is sound and correctly conservative. The primary risks are premature reuse enablement, ranking trustworthiness, and operational scale-up — not fundamental design flaws.

---

## Architecture Overview

### Module layers

| Layer | Responsibility | Key modules |
|-------|----------------|-------------|
| Identity & manifest | Path-free fingerprints, bridge manifest, idempotency keys | `profile_fingerprints.py`, `profile_candidate.py`, `profile_manifest_capture.py` |
| Creation & promotion | Snapshot from verified attempt → candidate → profile revision | `profile_creation.py`, `profile_lineage.py`, `profile_store.py` |
| Shadow observation | Pre-plan prediction, post-run comparison (never controls execution) | `profile_shadow.py`, `profile_shadow_eligibility.py`, `profile_shadow_ranking.py`, `profile_shadow_drift.py`, `profile_shadow_comparison.py` |
| Validation & gates | Scenario registration, labels, promotion metrics, scoped evidence | `profile_shadow_validation_*.py`, `validation/campaign_*.py` |
| Orchestrator seams | Four integration points in `BridgeOrchestrator` | `learning/orchestrator.py` |

### Data flow

```
BridgeOrchestrator.run
    │
    ├─► [before planner] ProfileShadowService.create_prediction
    │       list bundles → eligibility → drift → rank → select winner
    │       persist prediction + candidates (OBSERVE ONLY)
    │
    ├─► plan → execute → verify (VerificationGateway)
    │
    ├─► [on verified success] ProfileCandidateService.persist_from_verified
    │       capture_verified_manifest_context → build snapshot → persist candidate
    │       ProfileCreationService.promote → lineage attach/create
    │
    └─► [at finalize] ProfileShadowService.record_actual_outcome
            persist actual → build comparison metrics → persist comparison

Offline: ShadowValidationReporter.generate_scoped_report
    → ValidationEvidenceScope filter → metrics → evaluate_promotion_gates
```

### Database model

All tables live in shared SQLite (`outcomes.db`):

- **Profile (11 tables):** candidates, lineages, profiles, program/host/bridge/verification fingerprints, artifacts, invalidations, creation/candidate events
- **Shadow (5 tables):** predictions, candidates, actual outcomes, comparisons, events
- **Validation (4 tables):** scenarios, validation runs, labels, failure analysis

### Feature flags

| Flag | Default | Effect |
|------|---------|--------|
| `compatibility_profiles_enabled` | `false` | Master gate for candidate persistence |
| `compatibility_profile_creation_enabled` | `false` | Profile promotion |
| `compatibility_profile_shadow_mode` | `false` | Shadow prediction/comparison |
| `compatibility_profile_reuse_enabled` | `false` | **Active reuse — never enabled in production** |

---

## Strengths

### 1. Observe-only shadow mode (safety by construction)

Shadow predictions are created before planning but never feed back into the planner or executor. `ProfileShadowService` docstring and orchestrator wiring enforce this: no code path applies a predicted profile to an active run. Failures in shadow code are swallowed (`except Exception: pass`) so profile bugs cannot break bridge execution.

### 2. Layered content-addressed identity

Identity is built from path-free hashes: program identity → host class → bridge family → verification binding → lineage → idempotency. Disposable prefix paths are explicitly stripped from manifest identity (`_stable_env()` excludes `WINEPREFIX`). This prevents the WINEPREFIX identity-leak defect class that contaminated early pilot profiles.

### 3. Idempotent promotion with race safety

`promote_candidate_snapshot()` uses `BEGIN IMMEDIATE`, idempotency-key lookup, and `IntegrityError` retry to handle concurrent promotion. Outcomes are explicitly `"created"` or `"attached"`, enabling auditable duplicate-lineage metrics.

### 4. Deterministic eligibility and rejection

`evaluate_candidate_eligibility()` produces sorted, enumerated rejection reason codes across identity, host, wine, invalidation, manifest, binding, and artifact dimensions. Trust categories and `winner_selectable` are computed from explicit rules, not heuristics.

### 5. Evidence-gated promotion

Active reuse requires passing quantitative gates (`PromotionGateThresholds`: ≥50 comparisons, ≥10 drift/rejection scenarios, precision ≥0.95, duplicate rate = 0, etc.) with Wilson confidence intervals and per-category failure detection. Governance is encoded, not ad hoc.

### 6. Failure isolation on the hot path

Profile candidate persistence, promotion, and shadow recording all catch exceptions, log events, and increment counters without failing the bridge session. The subsystem degrades gracefully.

### 7. Immutable campaign evidence

Validation campaigns use append-only evidence with explicit scoping (`ValidationEvidenceScope`). Prior pilot evidence is never rewritten; corrections happen through inclusion/exclusion boundaries and evidence-quality classification.

### 8. Verification binding compatibility

Reuse eligibility re-checks verification policy/version/required-checks via `verification_binding_compatibility.py`. Profiles are bound to the verification contract that created them, aligned with ADR-001's authoritative verification boundary.

---

## Weaknesses

### 1. Ranking formula is hand-tuned and recency-biased

`profile_shadow_rank_v1` is a fixed-weight linear score (identity 0.20, host 0.15, recency 0.07, etc.) with a capped ML component (≤0.15). Pilot-004 Run J showed Candidate 2 winning primarily on recency (0.9996 vs 0.9957) with only a low-impact `WINEDLLOVERRIDES` manifest delta. The ranking-safety explanation classifies this as `RECENCY_ONLY_TIEBREAK` with `active_reuse_eligible=false`, but **selection still follows the raw score** — the safety classification is advisory metadata only.

### 2. Manifest capture was incomplete until Pilot-005

Pre-fix profiles stored `installed_components: []` because `persist_from_verified` did not capture prefix state. Drift detection used effective prefix observation while stored manifests lacked component data — causing Run 7 evidence to rely on drift-engine effective manifests rather than stored profile rows. `manifest_capture_v2` fixes forward capture; legacy profiles remain reconstruction-ineligible.

### 3. Single shared SQLite database

All profile, shadow, validation, and bridge session data share `outcomes.db` with `ensure_*_tables()` on every connection. Adequate at pilot scale; concurrency and query performance risk as profile count and shadow event volume grow. `list_profile_bundles_for_executable()` performs N+1 bundle loads.

### 4. Campaign scope is Pilot-004-specific

`build_evidence_scope()` only handles `shadow-validation-pilot-004`; other campaign IDs raise `ValueError`. Legacy profile UUIDs and excluded campaign IDs are hardcoded in `profile_shadow_validation_scope.py`. Necessary for immutability but brittle for multi-campaign operations.

### 5. Observe-only invariant is convention-enforced

No automated test asserts that the orchestrator cannot act on a shadow prediction. A future code change could silently wire prediction into planning. The invariant depends on developer discipline and code review, not structural enforcement.

### 6. Partial drift observation

Several drift dimensions are permanently `indeterminate` because shadow mode is read-only (cannot observe runtime mutations). `wrapper_versions` and `config_hashes` in manifest capture return empty. Drift prediction coverage is incomplete for active reconstruction scenarios.

### 7. Global vs scoped gate confusion (fixed, but operational risk remains)

Before Pilot-005, promotion gates aggregated all historical shadow evidence (unscoped duplicate rate 0.6452 across 31 comparisons). Scoped gates correctly show 9/9 comparisons but operators must always use `--campaign-id` to avoid pollution. Default CLI behavior still reports global metrics.

### 8. API/file-existence guard blocks known-failure scenarios

`/bridge/run` returns HTTP 404 when `file_path` does not exist, preventing API-path known-failure scenarios (Pilot-004 Run 9 required direct orchestrator bypass). This is an API design constraint, not a profile defect, but it complicates validation campaign design.

---

## Technical Debt

| Item | Severity | Location | Notes |
|------|----------|----------|-------|
| Hand-tuned ranking weights | Medium | `profile_shadow_ranking.py:122-135` | No calibration pipeline; recency overweighted for near-equivalent manifests |
| Ranking safety not enforced in selection | High | `select_predicted_winner()` | `active_reuse_eligible` is metadata; not a selection gate |
| Legacy profiles with empty components | Medium | DB `compatibility_profiles` | Require re-verification or remain shadow-only |
| Hardcoded scope exclusions | Low | `profile_shadow_validation_scope.py` | Legacy UUIDs, campaign IDs, fixture IDs |
| `ensure_*_tables()` per call | Low | All store modules | Schema self-healing but adds overhead |
| Incomplete manifest capture fields | Medium | `profile_manifest_capture.py` | `wrapper_versions`, `config_hashes` empty |
| 14 pre-existing test failures | Medium | `test_verification_authority`, `test_wine_gui_contract` | Present on freeze commit; unrelated to profile work but block clean CI |
| Design doc status drift | Low | `docs/design/compatibility-profile-design.md` | Marked "not approved for implementation" while code exists |
| Inline `import json` in hot path | Low | `profile_shadow.py` | Minor code smell |

---

## Architectural Risks

### R1: Premature active reuse enablement (Critical)

Scoped promotion gates fail on volume (9/50 comparisons), drift (2/10), rejection (4/10), and duplicate rate (8/9). Enabling `compatibility_profile_reuse_enabled` before Pilot-005 execution and gate passage would violate the evidence-gated governance model.

### R2: Recency-driven reuse without outcome history (High)

If reuse is enabled without enforcing `active_reuse_eligible` in winner selection, near-equivalent profiles differing only by recency or low-impact configuration could be actively applied. Pilot-004 demonstrated this exact scenario (Candidate 2 over Candidate 1).

### R3: Historical evidence pollution (Medium — mitigated)

Unscoped gate computation inflated duplicate rate to 0.6452. Scoped gates fix this, but any code path that forgets `ValidationEvidenceScope` or uses global metrics could reintroduce pollution. Legacy WINEPREFIX-leak profiles remain in DB, excluded only by scope lists.

### R4: Schema version mass-invalidation (Medium)

`manifest_capture_version`, `shadow_prediction_v1`, `bridge_manifest_v1`, and eligibility reason code enums create version gates. Bumping any schema without a migration path will mass-invalidate existing profiles (by design, but operationally disruptive).

### R5: SQLite concurrency at scale (Medium)

Profile promotion uses `BEGIN IMMEDIATE` but shadow prediction/comparison writes are concurrent with bridge sessions. High campaign volume (Pilot-005 target: ~48 runs) on a single writer may cause lock contention.

### R6: Shadow prediction timing vs prefix repair (Low — mitigated)

Pilot-004 required shadow prediction before wine-version repair to preserve drift evidence. This timing dependency is fragile: any orchestrator reordering could destroy pre-plan drift signals.

### R7: API guard vs validation campaign semantics (Low)

File-existence pre-check in `/bridge/run` prevents API-path known-failure scenarios. Workarounds (direct orchestrator, ntdll removal) exist but add campaign complexity.

---

## Simplification Opportunities

### S1: Enforce ranking safety at selection time

Instead of advisory `ranking_explanation` metadata, make `select_predicted_winner()` consult `active_reuse_eligible` when reuse is enabled. For shadow mode, this is a no-op; for active reuse, it becomes the enforcement gate. Eliminates the policy/metadata split.

### S2: Consolidate store `ensure_*_tables()` into startup migration

Run schema initialization once at application startup rather than on every `_connect()`. Reduces per-call overhead and clarifies migration ownership.

### S3: Generalize `ValidationEvidenceScope` builder

Replace `build_pilot004_evidence_scope()` with a campaign-manifest-driven builder that reads evidence-quality review JSON and completion reports for any campaign ID. Removes hardcoded UUIDs from Python source.

### S4: Extract ranking formula to configuration

Move `profile_shadow_rank_v1` weights to a versioned config file or DB table. Enables recalibration without code changes and supports A/B testing during shadow validation.

### S5: Unify manifest capture and drift observation

Single authoritative `read_prefix_state(prefix)` used by both manifest capture at creation time and drift prediction at shadow time. Eliminates the effective-manifest vs stored-manifest divergence class.

### S6: Campaign evidence as first-class orchestrator concern

Integrate `campaign_evidence.py` (`prepare_run_evidence_paths`, `persist_run_evidence`) into a campaign runner module rather than ad hoc executor scripts in `/tmp`. Reduces operational fragility (Pilot-004 Run 10 directory bug).

### S7: Separate shadow DB or read-replica

For production scale, shadow/validation tables could move to a separate SQLite file or read-replica to isolate write contention from bridge session hot path.

---

## Recommendations

### Immediate (before any reuse consideration)

1. **Complete Pilot-005 execution** — Close volume gaps (≥50 comparisons, ≥10 drift, ≥10 rejection) with diverse scenarios across T1/T2/T3/32-bit targets.
2. **Enforce ranking safety in selection** — Wire `active_reuse_eligible` as a hard gate in `select_predicted_winner()` before reuse flag can be enabled.
3. **Re-verify legacy profiles** — Profiles without `manifest_capture_v2` should remain shadow-observation-only until re-verified with complete component capture.
4. **Fix pre-existing test failures** — 14 failures in `test_verification_authority` / `test_wine_gui_contract` block clean CI on freeze commit.

### Short-term (Pilot-005 freeze → execution)

5. **Generalize evidence scope** — Campaign-manifest-driven `ValidationEvidenceScope` builder for Pilot-005 and beyond.
6. **API-compatible known-failure scenario** — Replace executable-deletion approach with ntdll-removal (proven in precondition script); no product bypass.
7. **Integrate campaign evidence tooling** — Atomic evidence persistence in campaign runner, not ad hoc scripts.
8. **Default CLI to scoped gates** — `gates` command should require `--campaign-id` or warn when reporting global metrics.

### Medium-term (post-promotion-gate passage)

9. **Ranking formula calibration** — Replace hand-tuned weights with outcome-history-driven calibration; reduce recency weight for near-equivalent manifests.
10. **Schema migration tooling** — Versioned migration path for manifest capture, shadow prediction schema, and eligibility reason codes.
11. **Structural observe-only enforcement** — Test that orchestrator cannot consume shadow predictions; consider interface segregation (prediction writer vs plan consumer).
12. **Profile store query optimization** — Batch bundle loading, index tuning, or separate store for shadow events.

### Long-term (active reuse production)

13. **Active reuse with verification re-check** — Reuse applies manifest reconstruction then re-verifies through `VerificationGateway` before `SUCCEEDED`.
14. **Outcome-history accumulation** — Track per-profile reuse success rate, failure rate, and performance limits to feed ranking and reuse decisions.
15. **Multi-campaign evidence aggregation** — Scoped gates composable across campaigns for cumulative promotion evidence.

---

## Estimated Effort

| Work item | Effort | Depends on |
|-----------|--------|------------|
| Pilot-005 campaign execution (~48 runs) | 2–3 days | Freeze approval, snapshot prep |
| Ranking safety enforcement in selection | 0.5 day | — |
| Generalize evidence scope builder | 1 day | Pilot-005 manifest |
| Campaign evidence runner integration | 1 day | — |
| API known-failure scenario + proof | 0.5 day | Wine environment |
| Legacy profile re-verification plan | 1 day | Manifest capture v2 deployed |
| Pre-existing test failure triage | 1–2 days | Root cause analysis |
| Ranking formula calibration pipeline | 3–5 days | Sufficient outcome history |
| Schema migration tooling | 2–3 days | — |
| Observe-only structural enforcement | 1 day | — |
| Profile store performance optimization | 2–3 days | Volume thresholds |
| Active reuse implementation | 5–8 days | All promotion gates passed |

**Total to promotion-ready:** ~8–12 days (Pilot-005 execution + enforcement + tooling)  
**Total to active reuse production:** ~20–30 days additional (after gate passage)

---

## Priority Order

| Priority | Item | Rationale |
|----------|------|-----------|
| **P0** | Keep active reuse disabled | Governance requirement; Pilot-004 classification |
| **P0** | Execute Pilot-005 shadow validation | Only path to close volume gate shortfalls |
| **P1** | Enforce ranking safety at selection | Blocks recency-only reuse defect class |
| **P1** | Manifest capture v2 on all new profiles | Closes Run 7 effective-vs-stored manifest gap |
| **P1** | Campaign evidence tooling integration | Prevents Run 10-class persistence failures |
| **P2** | Generalize evidence scope | Required for Pilot-005+ campaigns |
| **P2** | API-compatible known-failure scenario | Replaces exploratory Run 9 approach |
| **P2** | Fix pre-existing test failures | Clean CI baseline |
| **P3** | Default CLI to scoped gates | Operator safety |
| **P3** | Legacy profile re-verification | Reconstruction eligibility |
| **P4** | Ranking formula calibration | Improves winner quality post-reuse |
| **P4** | Schema migration tooling | Operational safety at scale |
| **P5** | Store performance optimization | Needed at production volume only |
| **P5** | Active reuse implementation | Only after all promotion gates pass |

---

## Appendix: Pilot-004 Scoped Gate Snapshot

From `data/validation/evidence/pilot-004/scoped-gates.json` (post Pilot-005 corrective scoping):

| Gate | Result | Threshold |
|------|--------|-----------|
| Labelable comparisons | 9 / 9 | ≥ 50 |
| Drift scenarios | 2 / 2 | ≥ 10 |
| Rejection scenarios | 4 / 4 | ≥ 10 |
| Program kinds | 3 / 3 | ≥ 3 ✓ |
| Scenario categories | 9 / 9 | ≥ 5 ✓ |
| Eligibility precision | 100% | ≥ 95% ✓ |
| False eligibility rate | 0% | ≤ 5% ✓ |
| Drift false-positive rate | 0% | ≤ 5% ✓ |
| Rank agreement | 100% | ≥ 80% ✓ |
| Duplicate profile rate | 8 / 9 (88.9%) | 0% |

**Classification:** `COMPLETED_NOT_PROMOTION_READY`  
**Excluded from scope:** Run 9 (exploratory), Pilot-001/002/003, legacy WINEPREFIX-leak profiles, controlled duplicate fixture B

---

## References

- `docs/design/compatibility-profile-design.md` — Domain model and lifecycle design
- `docs/adr/ADR-001-authoritative-bridge-lifecycle.md` — Verification boundary prerequisite
- `docs/operations/shadow-validation-runbook.md` — Operational procedures
- `data/validation/campaigns/pilot-004-evidence-quality-review.json` — Immutable run classification
- `data/validation/campaigns/pilot-005-package.md` — Corrective engineering index
- `data/validation/campaigns/pilot-005-ranking-safety.md` — Active reuse ranking policy
- `data/validation/campaigns/pilot-005-continuity-policy.md` — Campaign evidence immutability rules
