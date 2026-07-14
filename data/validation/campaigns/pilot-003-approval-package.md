# Pilot-003 Corrective Approval Package

**Date:** 2026-07-14  
**Status:** `corrective_package_pending_approval` — **DO NOT EXECUTE Pilot-003 until explicitly approved**  
**Predecessor:** `shadow-validation-pilot-002` → `aborted_non_promotable` / `SCENARIO_ID_MANIFEST_MISMATCH`

---

## 1. Pilot-002 closure record

| Field | Value |
|-------|-------|
| Terminal status | `aborted_non_promotable` |
| Abort reason | `SCENARIO_ID_MANIFEST_MISMATCH` |
| Started (UTC) | `2026-07-14T00:57:10Z` |
| Stopped (UTC) | `2026-07-14T01:01:09Z` |
| Completed runs | 1–6 (Bridge succeeded) |
| Registered runs | 1–5 |
| Unregistered completed run | 6 (`E_prefix_drift` — not in manifest) |
| Not started | 7–12 |
| Final DB hash | `0bd2371d634463fbe40e640787a0dd506832189856232c8bd29e54c05a1484ad` |
| Source snapshots at abort | T2 `ee165aaa…`, T3 `2ef515d4…` (verified intact) |
| Promotion eligible | **false** |
| Active reuse | **false** (unchanged) |
| Closure record | `data/validation/campaigns/shadow-validation-pilot-002-closure.json` |

Run 6 evidence preserved at `data/validation/evidence/pilot-002/run-06/` — **not retroactively registered**.

---

## 2. Scenario-ID root cause

Pilot-002 matrix Run 6 used `scenario_id: E_prefix_drift` (category label). Frozen manifest `shadow_scenario_manifest_v1.json` registers only:

- `E_prefix_drift_windows`
- `E_prefix_drift_component`

`register-run` correctly rejected the unknown ID. This is a **pre-freeze input defect**, not a runtime Bridge failure.

**Corrective action:** Pilot-003 splits drift into Runs 6–7 with explicit manifest IDs. Pre-freeze validator now refuses packages containing unknown matrix scenario IDs.

---

## 3. Verification-binding root cause

### Observed (Runs 1–6)

| Metric | Value |
|--------|-------|
| `selected_profile_id` | **null** all runs |
| T2 candidate count (runs 1–4, 6) | 3 per run (canonical + 2 legacy) |
| Run 5 candidate count | **0** (notepad32 hash — no matching profiles) |
| Primary rejection | `VERIFICATION_BINDING_INCOMPATIBLE` (aggregate only in Pilot-002) |

### Root cause

`profile_shadow_eligibility` compared stored profile policy (`wine_gui_process_v1`) against a **hardcoded** `bridge_aggregate_v1` binding. Wine GUI profiles are correct; the shadow pre-plan checker was wrong.

Successful setup/execution used:

- `policy_id: wine_gui_process_v1`
- `phase: wine_gui`
- checks: `process_survives`, `target_process_identity`

### Fix (pattern C — smallest architecture-consistent)

`ExpectedVerificationContract` is inferred from `classify_program_kind()` **before planning** (no `planner.plan()`, no execution-path changes). `evaluate_verification_binding_compatibility()` applies deterministic rules with detailed reason codes.

---

## 4. Compatibility-rule design

| Class | Rule |
|-------|------|
| **Exact compatible** | Same policy ID, compatible version, stored checks ⊇ expected checks, binding key reconstructs |
| **Semantically compatible** | Explicit registry entry in `SEMANTIC_POLICY_COMPATIBILITY` only |
| **Incompatible** | Policy ID mismatch, version mismatch, required checks removed, verifier binding drift, known program-kind conflict, unknown policy |

**Reason codes (persisted):**

- `VERIFICATION_POLICY_ID_MISMATCH`
- `VERIFICATION_POLICY_VERSION_INCOMPATIBLE`
- `REQUIRED_CHECKS_MISMATCH`
- `VERIFIER_VERSION_INCOMPATIBLE`
- `VERIFICATION_PHASE_MISMATCH`
- `VERIFICATION_POLICY_UNKNOWN`
- `VERIFICATION_BINDING_INCOMPATIBLE` (aggregate when detailed reasons exist)

---

## 5. Timing / refinement design

Shadow prediction runs **before** normal planning. Final verification contract for Wine GUI is knowable from program inspection (`pe_windows_gui` → `wine_gui_process_v1` / `wine_gui` phase). **Pattern C** — no second planner pass, no profile promotion to control path.

---

## 6. Tests

| Suite | Result |
|-------|--------|
| Focused corrective | 16 passed (`test_campaign_freeze_validator`, `test_verification_binding_compatibility`, Run F invariant) |
| Architecture invariants | included in full suite |
| **Full suite** | **576 passed, 0 failed** |

New tests cover: Pilot-002 mismatch detection, Wine GUI eligibility, T2/T3 isolation, policy/version/check rejection, detailed reason persistence, pre-freeze validator failures.

---

## 7. Corrected Pilot-003 matrix (13 runs)

| # | Scenario ID | Target |
|---|-------------|--------|
| 1 | `A_stable_repeat_success` | T2 |
| 2 | `B_relocated_executable` | T2 |
| 3 | `C_compatible_host_drift` | T2 |
| 4 | `D_incompatible_host_drift` | T2 |
| 5 | `D_incompatible_host_drift` | T3-arch notepad32 |
| 6 | `E_prefix_drift_windows` | T2 |
| 7 | `E_prefix_drift_component` | T2 |
| 8 | `F_clean_prefix_reconstruction` | T2 |
| 9 | `G_known_compatibility_failure` | T3 WordPad |
| 10 | `H_unrelated_runtime_failure` | T1 native timeout |
| 11 | `I_trust_state_imported` | T2 |
| 12 | `I_trust_state_invalidated` | T2 |
| 13 | `J_multiple_candidate_ranking` | T2 |

Matrix file: `data/validation/campaigns/pilot-003-matrix.json`

---

## 8. Pre-freeze validator output

```bash
alma-bridge-shadow-validation validate-freeze
```

**Matrix / scenario / flags / exclusion checks:** PASS (when snapshots pending)  
**Blocking until Pilot-003 freeze:** `SOURCE_SNAPSHOT_MISSING` for `pilot-003/snapshots/*` (expected — snapshots captured at freeze, not before corrective commit)

Validator command: `validate-freeze` on `alma-bridge-shadow-validation`.

---

## 9. Profile eligibility (post-fix, live DB)

| Profile | Matching run | Eligible? |
|---------|----------------|-----------|
| T2 canonical `a5576257…` | T2 notepad64 / `pe_windows_gui` | **yes** |
| T3 canonical `281e69a0…` | T3 wordpad64 / `pe_windows_gui` | **yes** |
| T2 on T3 program identity | cross-match | **rejected** (`PROGRAM_IDENTITY_MISMATCH`) |
| Native test profile | Wine GUI contract | **rejected** (`VERIFICATION_POLICY_ID_MISMATCH`) |

No profile becomes eligible from executable basename alone.

---

## 10. Pilot-002 exploratory analysis (engineering only)

### Why `selected_profile_id` was null

All T2 runs: 3 candidates evaluated, all rejected `VERIFICATION_BINDING_INCOMPATIBLE` due to hardcoded `bridge_aggregate_v1` checker. **Corrected logic would select canonical T2** (`a5576257…`) for runs 1–4 and 6.

### Run 5 (D incompatible-host, notepad32)

0 candidates — no profiles indexed for PE32 notepad hash. Bridge still succeeded via planner default. Shadow had nothing to rank; not a binding defect.

### Runs 4–5 (incompatible-host scenarios, Bridge succeeded)

- **Run 4:** Host metadata simulation did not induce `WINE_MAJOR_INCOMPATIBLE` / capability loss on this single host. Shadow rejected profiles for **binding incompatibility**, not host class. Bridge planner succeeded independently — **valid divergence** (shadow ≠ execution control).
- **Run 5:** Architecture mismatch scenario used different executable; no profile candidates existed. Bridge success does **not** imply shadow rejection was wrong.

### Compatible / incompatible-host intent

Runs 4–5 did **not** fully induce incompatible-host conditions. Host-class logic was never reached because binding rejection dominated. Pilot-003 binding fix enables host-class scenarios to be evaluated as designed.

---

## 11. Freeze artifacts (pending execution approval)

| Artifact | SHA-256 |
|----------|---------|
| `shadow-validation-pilot-003.json` | `111a30a0a98cad68a35a153d8176094d73a74bb8ce20326f60d1fc7a921a1d9c` |
| `pilot-003-matrix.json` | `391344363be18c9d2cf4da303788d06647b47a918f3c4c239b3a98c2e35c5c88` |
| `shadow_scenario_manifest_v1.json` | `8a0f95a46ccadd57665f0a24e6b6eeb4fd8d6c6a17a3d97aa9ce6a10f4dabf28` |

### DB backup plan (at Pilot-003 freeze)

```bash
cp data/outcomes.db "data/validation/backups/outcomes.db.pilot-003-freeze.$(date -u +%Y%m%dT%H%M%SZ)"
sha256sum data/validation/backups/outcomes.db.pilot-003-freeze.*
```

Current DB (post Pilot-002 abort): `0bd2371d634463fbe40e640787a0dd506832189856232c8bd29e54c05a1484ad`

### Source snapshots

Pilot-002 reference hashes: T2 `ee165aaa…`, T3 `2ef515d4…`.  
Pilot-003 requires **new snapshots** under `~/.local/share/alma-bridge/prefixes/validation/pilot-003/snapshots/` at freeze with recorded aggregate hashes.

---

## 12. Confirmations

| Item | Status |
|------|--------|
| Pilot-002 evidence excluded from promotion gates | ✓ |
| Pilot-002 DB/evidence preserved | ✓ |
| Active reuse disabled | ✓ |
| Shadow does not call `planner.plan()` | ✓ |
| Pilot-003 **not executed** | ✓ BLOCKED |

**Pilot-003 scenario execution remains BLOCKED until operator explicitly approves this package.**
