# Pilot-003 Final Freeze Approval Package

**Date:** 2026-07-14  
**Status:** `ready_for_execution_approval` — **scenario execution NOT APPROVED**  
**Corrective commit:** `6bf06ca14e760a4f976279f1ee9fd201dffa2080`  
**Freeze commit:** _(recorded at commit time)_

---

## 1. Pilot-002 closure (unchanged)

| Field | Value |
|-------|-------|
| Status | `aborted_non_promotable` |
| Reason | `SCENARIO_ID_MANIFEST_MISMATCH` |
| Evidence | Excluded from promotion gates |
| Active reuse | **false** |

Record: `data/validation/campaigns/shadow-validation-pilot-002-closure.json`

---

## 2. Git / tree

| Item | Value |
|------|-------|
| Corrective SHA | `6bf06ca14e760a4f976279f1ee9fd201dffa2080` |
| Historical doc commit | `f2d9ab5` (Pilot-002 execution approval package) |
| Working tree | Clean before freeze commit |
| Secret scan | SECRET_SCAN_CLEAN (no credentials in freeze artifacts) |

---

## 3. Authoritative tests (from freeze commit)

| Suite | Result | Runtime |
|-------|--------|---------|
| Focused (freeze/validator/binding/shadow/wine_gui) | **48 passed, 0 failed** | ~29 s |
| Full `PYTHONPATH=. pytest -q` | **576 passed, 0 failed** | ~1084 s (~18:04) |

---

## 4. Pre-freeze validator (zero errors)

```
alma-bridge-shadow-validation validate-freeze
→ passed: true, issues: []
```

---

## 5. Run 4 — incompatible host

| Field | Value |
|-------|-------|
| Candidate | T2 canonical `a5576257…` |
| Induced mismatch | Shadow `host_payload_overlay.host_arch=aarch64` vs profile `x86_64` |
| Expected reason | **`HOST_ARCH_MISMATCH`** |
| Physical host | Unchanged |

---

## 6. Run 5 — architecture variant

| Field | Value |
|-------|-------|
| Objective | Host architecture mismatch with **existing** candidate |
| Executable | PE32 notepad32 `503665cb…` |
| Profile | `9c96be17-46eb-46d7-ba0b-9c404f97bf80` |
| Induced mismatch | Shadow `host_arch=aarch64` vs profile `x86_64` |
| Expected reason | **`HOST_ARCH_MISMATCH`** |

---

## 7. Verification-binding eligibility audit

Artifact: `data/validation/campaigns/pilot-003-eligibility-audit.json`  
SHA-256: `763b7439801e7414a55c7e6a3c646f6fc4d984a90b8dfb2d2af4a98c614dd307`  
Result: `all_passed: true`

---

## 8. Source snapshots

Registry: `data/validation/campaigns/pilot-003-source-snapshots.json`

| Snapshot | Aggregate SHA-256 | Executable SHA-256 |
|----------|-------------------|-------------------|
| T2 notepad64 | `0cbbe4a348ae907f0f1cce8c9c1d1d73079c725e79569a6355e323e3a7ff6c8e` | `108168df…` |
| T3 wordpad64 | `2e482c17aaacdf5d2f55153174c0494d2ae8904ff339f0c63a2a5c5eda4a8607` | `a2bddbb8…` |
| T3 notepad32 | `874d2d41c96867efc302222fe2212048ccb83e498bdd0db72555d4cc79e6eed2` | `503665cb…` |

Wine: `wine-9.0 (Ubuntu 9.0~repack-4build3)` | Guard root: `…/pilot-003/snapshots`

---

## 9. Database

| Item | SHA-256 |
|------|---------|
| Live DB (pre-campaign) | `fde1f6dee2174bf303fbb416adc035f0802ef11ef02e3b8902fb6b1b63cc4b1b` |
| Backup | `outcomes.db.pilot-003-freeze.20260714T041429Z` (same hash) |

---

## 10. Campaign input hashes

| Input | SHA-256 |
|-------|---------|
| `shadow-validation-pilot-003.json` | `99e8cc9a8af0c71caf17739018baebf142d92f344e9e189a4b38656368fb1d49` |
| `pilot-003-matrix.json` | `a405fe85d07d3a47215a32b890543405689fc9ea55fae3521979e042dd938051` |
| `pilot-003-commands.md` | `c869078369ef88391adbd4690bc8a4eca398cf05c68b05c365f2dba94755f1e7` |
| `pilot-003-freeze-package.md` | `9ca1ac625c41124f8ed46191512a8ddb5910cf730f3d0e8cb911ce717743daa1` |
| `pilot-003-eligibility-audit.json` | `763b7439801e7414a55c7e6a3c646f6fc4d984a90b8dfb2d2af4a98c614dd307` |
| `pilot-003-source-snapshots.json` | `be10ffeacc3a03c7169b5de402c9fc44f4b96c0ba82d2c1ed56fd20c49d1e9da` |
| `shadow_scenario_manifest_v1.json` | `8a0f95a46ccadd57665f0a24e6b6eeb4fd8d6c6a17a3d97aa9ce6a10f4dabf28` |
| Legacy exclusion set | `a27772519ef1def67dcf34a674b28109ca62beef1cc06fc1ff977fedc83e286f` |

---

## 11. Run J plan

- Candidate 1: canonical T2 `a5576257…`
- Candidate 2: produced by **Run 6** (`E_prefix_drift_windows`) via material `windows_version` manifest drift
- Run 13: **BLOCKED_PRECONDITION** until SQL query returns `eligible_count >= 2` and `distinct_manifests >= 2`

---

## 12. Confirmations

| Item | Status |
|------|--------|
| Pilot-001 evidence excluded | ✓ |
| Pilot-002 evidence excluded | ✓ |
| Ascension research-only | ✓ |
| Active reuse disabled | ✓ |
| Run F shadow-only invariant | ✓ |
| Pilot-003 **not executed** | ✓ BLOCKED |

**Scenario execution remains blocked until explicit operator approval.**
