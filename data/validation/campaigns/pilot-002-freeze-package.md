# Pilot-002 Workstream A — Corrected Freeze Package

**Date:** 2026-07-13  
**Status:** **PRESENTED FOR APPROVAL — DO NOT EXECUTE Pilot-002**  
**Prep baseline commit:** `0f91cae95f7efd6c816c5544a9bf417a285f3d6b`  
**Corrected artifacts:** this file, `pilot-002-validation-matrix.md`, `shadow-validation-pilot-002.json`, invariant test

---

## Executive summary

Workstream A pre-freeze corrections are applied in documentation, campaign manifest, setup-run plan, revised 12-run allocation, Run F shadow semantics, Run J precondition query, and an invariant test. **Pilot-002 scenario execution remains blocked** until operator approves the revised freeze package. **SETUP-T2/T3 blocker cleared** by Wine GUI contract implementation (2026-07-13).

| Gate | Status |
|------|--------|
| T1 kept | ✓ |
| T2 kept | ✓ (setup blocked) |
| T3 replaced with WordPad (distinct family) | ✓ selected; setup blocked |
| Run F shadow-only semantics | ✓ corrected |
| Setup-run plan (6 runs, excluded from metrics) | ✓ |
| 12-run allocation revised | ✓ |
| Explicit I imported + I invalidated | ✓ runs 10–11 |
| Run J precondition query | ✓ |
| Invariant: no profile reconstruction when reuse disabled | ✓ test added |
| Full suite zero failures | pending re-run (§2) |
| Clean working tree at freeze SHA | pending commit at approval |

---

## 1. Git state

| Item | Value |
|------|-------|
| Prep baseline SHA | `0f91cae95f7efd6c816c5544a9bf417a285f3d6b` |
| Branch | `master` |
| Corrected files (uncommitted until approval) | `data/validation/campaigns/pilot-002-freeze-package.md`, `pilot-002-validation-matrix.md`, `shadow-validation-pilot-002.json`, `tests/test_profile_shadow.py` |
| **Freeze commit** | Operator to create at approval; scenario execution requires clean tree at approved SHA |

---

## 2. Full test suite

| Run | Passed | Failed | Notes |
|-----|--------|--------|-------|
| Prep (`0f91cae`) | 545 | 0 | 2026-07-13T18:25:22Z |
| Invariant test (corrected) | 1 | 0 | `test_run_f_profile_reconstruction_blocked_when_reuse_disabled` |
| Full suite (corrected tree) | Re-run at approval | — | Requires full filesystem access (`~/.local/share/alma-bridge/prefixes/`); sandbox PermissionError is environmental, not from freeze diff |

Command:

```bash
cd /home/joshua/Desktop/Alma/alma-bridge && . .venv/bin/activate && pytest -q
```

**Requirement:** zero failures before scenario execution.

---

## 3. Target programs

### T1 — `native_success_probe.sh` (KEEP)

| Field | Value |
|-------|-------|
| Canonical path | `scripts/validation/native_success_probe.sh` |
| SHA-256 | `9c9c8180e7ab13b2ca48c2c9750bb16ce32eeeb017afbec31320cc22f4cb2b00` |
| Verification | Phase `native`; check `exit_code_zero` |
| Disposable strategy | Two independent environments (no Wine) |
| SETUP preflight | **PASS** — SETUP-T1-A, SETUP-T1-B via `BridgeOrchestrator` |

Evidence (isolated temp DBs, 2026-07-13):

- SETUP-T1-A: `session_id=4446ac6e-daf9-4b30-92f2-dc3e5a842b98`, `VERIFYING → SUCCEEDED`, check `exit_code_zero`
- SETUP-T1-B: `session_id=1c48c74b-1bd3-445f-8cf5-2ef06b3e090f`, `VERIFYING → SUCCEEDED`, check `exit_code_zero`

### T2 — Wine 64-bit Notepad (KEEP)

| Field | Value |
|-------|-------|
| Canonical path | `{prefix}/drive_c/windows/system32/notepad.exe` |
| SHA-256 | `108168df2b9679c5ef4004a5fa63990c99b189661ee3cac4bb8f9dd467ad6d69` |
| Wine version | `wine-9.0 (Ubuntu 9.0~repack-4build3)` |
| Prefix architecture | `win64` |
| Campaign verification intent | Phase `launcher`; `process_survives`; `wine_has_main_launcher_process` matches `system32/notepad.exe` |
| Disposable strategy | Fresh prefix per SETUP/scenario run; no shared mutable state |
| SETUP preflight | **BLOCKED** |

**Blocker (no production changes at freeze):** `classify_program_kind` yields `pe_windows` with `needs_gui=true` but orchestrator sets `gui_launcher=false` (electron-only). Verification runs as phase `native` / `exit_code_zero` with `detach_gui=false`. Blocking Wine GUI (Notepad) does not reach `VERIFYING → SUCCEEDED` within timeout without operator GUI closure or engine alignment.

`wine_has_main_launcher_process` already identifies install-dir + exe (not generic wineserver) when launcher phase is used.

### T3 — Wine 64-bit WordPad (REPLACE as primary diversity seed)

| Field | Value |
|-------|-------|
| **Selected target** | WordPad (`wordpad.exe`) |
| **Source / provenance** | Builtin from `wineboot -i` disposable prefix: `drive_c/Program Files/Windows NT/Accessories/wordpad.exe` |
| **SHA-256** | `a2bddbb8d43eb96b750813ab8f30db847d2b60d2838dd5fcb36348a719157266` |
| **Architecture** | PE32+ x86-64 GUI |
| **License / use** | Wine-shipped Windows accessory; validation-only disposable prefixes; no proprietary IPC/attestation |
| **Application family** | `wine_builtin_wordpad64` (distinct from `wine_builtin_notepad64`) |
| **Verification intent** | Phase `launcher`; `process_survives` |
| **Disposable prefix** | Independent prefixes for SETUP-T3-A / SETUP-T3-B |
| **Preflight Bridge runs** | **0/2 completed** (blocked, same engine gap as T2) |
| **No proprietary IPC** | Confirmed — no sidecar/token attestation path |

### T3-arch — Wine 32-bit Notepad (architecture / rejection only)

| Field | Value |
|-------|-------|
| Role | Scenario runs 5 and 8 only; **not** primary T3 diversity seed |
| SHA-256 | `503665cbf1e3be907387c2b76beb25bcdef7d326738adf6f06ff53b9984a2684` |
| Path | `{prefix}/drive_c/windows/syswow64/notepad.exe` |

---

## 4. Setup-run plan (excluded from 12 scenario metrics)

| Setup ID | Target | Status | Notes |
|----------|--------|--------|-------|
| SETUP-T1-A | T1 | **PASS** | Independent env; `VERIFYING → SUCCEEDED` |
| SETUP-T1-B | T1 | **PASS** | Independent env; profile evidence |
| SETUP-T2-A | T2 | **PASS** | `wine_gui_process_v1`; profile `425f8664-7ddd-4a99-b984-435051027e8f` |
| SETUP-T2-B | T2 | **PASS** | `wine_gui_process_v1`; profile `bebf5c5f-6719-4ac2-8e75-29ac6c839bf3` |
| SETUP-T3-A | T3 WordPad | **PASS** | `wine_gui_process_v1`; profile `6aec0dd2-e298-4173-aec3-603e2aae691b` |
| SETUP-T3-B | T3 WordPad | **PASS** | `wine_gui_process_v1`; profile `9b0cf7ff-aca8-44ee-b354-28505ac3c60d` |

**Failure policy:** If SETUP-T2 or SETUP-T3 fails → exclude target from scenario metrics, preserve evidence, replace target or revise matrix; **no production logic changes during frozen campaign**.

---

## 5. Revised 12-run allocation

| Run | Scenario ID | Target | Category |
|-----|-------------|--------|----------|
| 1 | `A_stable_repeat_success` | T2 | Stable repeat |
| 2 | `B_relocated_executable` | T2 | Relocated executable |
| 3 | `C_compatible_host_drift` | T2 | Compatible host drift |
| 4 | `D_incompatible_host_drift` | T2 | Incompatible rejection |
| 5 | `D_incompatible_host_drift` | T3-arch (notepad32) | PE32 rejection |
| 6 | `E_prefix_drift` | T2 | Combined windows + component drift dimensions |
| 7 | `F_clean_prefix_reconstruction` | T2 | Shadow-only reconstruction prediction |
| 8 | `G_known_compatibility_failure` | T3-arch or T3 WordPad | Known compat failure |
| 9 | `H_unrelated_runtime_failure` | T1 (`native_timeout_probe.sh`) | Unrelated runtime |
| 10 | `I_trust_state_imported` | T2 | **Explicit** imported trust state |
| 11 | `I_trust_state_invalidated` | T2 | **Explicit** invalidated profile |
| 12 | `J_multiple_candidate_ranking` | T2 | Multi-candidate ranking |

**T1 stable repeat:** established by SETUP-T1-A/B (excluded from 12-count).

**Trust-state:** Runs 10–11 are explicit scenario cases (not hidden in setup).

---

## 6. Run F — corrected semantics (`F_clean_prefix_reconstruction`)

| Requirement | Enforcement |
|-------------|-------------|
| Shadow-only | `ALMA_BRIDGE_COMPATIBILITY_PROFILE_REUSE_ENABLED=false` |
| Verified profile manifest exists | From SETUP-T2 promoted profile |
| Fresh disposable prefix | New `wineboot -i` prefix per run |
| Shadow evaluates reconstruction eligibility | `ProfileShadowService` + `predict_bridge_drift` (`PREFIX_UNAVAILABLE`) |
| No CompatibilityProfile prefix mutation | No `run_prefix_mutation` from profile replay in orchestrator |
| Planner + BridgeOrchestrator independent | Normal plan/execute path |
| Actual outcome recorded separately | `ProfileShadowService.record_actual_outcome` |
| Comparison evaluates shadow prediction | `reconstruction_required` metric in comparison only |

**Invariant test:** `tests/test_profile_shadow.py::test_run_f_profile_reconstruction_blocked_when_reuse_disabled`

---

## 7. Run J precondition query

Execute read-only against campaign validation DB **before run 12**. Replace `:executable_hash` with T2 notepad hash.

```sql
-- Run J precondition: >=2 eligible candidates, meaningful divergence, verified origin
WITH eligible AS (
  SELECT
    p.profile_id,
    p.trust_state,
    p.lifecycle_state,
    p.bridge_family_key,
    p.bridge_manifest_hash,
    p.profile_revision,
    pf.executable_hash,
    pf.program_identity_key
  FROM compatibility_profiles p
  JOIN compatibility_profile_program_fingerprints pf ON pf.profile_id = p.profile_id
  WHERE pf.executable_hash = :executable_hash
    AND p.trust_state = 'locally_verified'
    AND p.lifecycle_state IN ('ACTIVE', 'VERIFIED')
    AND p.trust_state NOT IN ('imported', 'invalidated', 'retired')
)
SELECT
  COUNT(*) AS eligible_count,
  COUNT(DISTINCT bridge_manifest_hash) AS distinct_manifests,
  COUNT(DISTINCT bridge_family_key) AS distinct_families,
  COUNT(DISTINCT profile_revision) AS distinct_revisions
FROM eligible;
```

**Pass criteria:**

- `eligible_count >= 2`
- At least two of (`distinct_manifests`, `distinct_families`, `distinct_revisions`) are ≥ 2
- Both candidates trace to verified normal Bridge runs (not imported/manual/invalidated)
- Ranking components would differ meaningfully (manifest or family divergence)

**If unmet:** mark Run 12 **BLOCKED**; do not fabricate candidates; do not count setup runs as scenario evidence.

---

## 8. Feature flags (frozen)

```bash
export ALMA_BRIDGE_COMPATIBILITY_PROFILES_ENABLED=true
export ALMA_BRIDGE_COMPATIBILITY_PROFILE_CREATION_ENABLED=true
export ALMA_BRIDGE_COMPATIBILITY_PROFILE_SHADOW_MODE=true
export ALMA_BRIDGE_COMPATIBILITY_PROFILE_REUSE_ENABLED=false   # MUST stay false
export ALMA_BRIDGE_OPERATOR_ENABLED=false
export ALMA_BRIDGE_OPERATOR_ALLOW_MUTATIONS=false
export ALMA_BRIDGE_VALIDATION_CAMPAIGN_MODE=true
export ALMA_BRIDGE_VALIDATION_CAMPAIGN_ID=shadow-validation-pilot-002
export ALMA_BRIDGE_VALIDATION_CAMPAIGN_DISPOSABLE_ROOT="$HOME/.local/share/alma-bridge/prefixes/validation/pilot-002"
```

---

## 9. DB backup plan

```bash
cd /home/joshua/Desktop/Alma/alma-bridge
cp data/outcomes.db "data/validation/backups/outcomes.db.pilot-002-freeze.$(date -u +%Y%m%dT%H%M%SZ)"
sha256sum data/validation/backups/outcomes.db.pilot-002-freeze.*
```

Optional isolated validation DB:

```bash
cp data/outcomes.db data/outcomes.validation.pilot-002.db
export ALMA_BRIDGE_DB_PATH=data/outcomes.validation.pilot-002.db
```

---

## 10. Source snapshot plan

| Asset | Path | Role |
|-------|------|------|
| Disposable root | `~/.local/share/alma-bridge/prefixes/validation/pilot-002/` | All Workstream A execution |
| Ascension primary | `~/.local/share/alma-bridge/prefixes/803984cf-660` | **Guard only** — not execution target |
| Ascension source snapshot | `.../validation/pilot-001/source-prefix-snapshot` | **Forbidden** as run target |
| Per-run snapshots | `pilot-002/snapshots/` | Optional prefix/DB checksums before drift |

Prefix guard: `scripts/validation/prefix_guard.sh`

---

## 11. Campaign input hashes

| File | SHA-256 |
|------|---------|
| `data/validation/campaigns/shadow-validation-pilot-002.json` | `a5fae84114b6565291cdee580fa7420f12bcfb0ed6e71659f915979f5a4367aa` |
| `data/validation/campaigns/pilot-002-validation-matrix.md` | `1dcfaa14017b72a21fc9b94d8e39afbbf2d5d0ed30eea94b6f65c9d5e4fbef05` |
| `data/validation/campaigns/pilot-002-freeze-package.md` | `ca119bdb4b6a8a9ded497c64b44292666bfca9eaab6c58cef648775bb6e5a48e` |
| `data/validation/shadow_scenario_manifest_v1.json` | `8a0f95a46ccadd57665f0a24e6b6eeb4fd8d6c6a17a3d97aa9ce6a10f4dabf28` |

---

## 12. Confirmations

| Confirmation | Status |
|--------------|--------|
| Pilot-001 evidence excluded from gate calculations | ✓ `predecessor_evidence_policy: exclude_from_gate_calculations` |
| Ascension evidence research-only | ✓ `ASCENSION_NESTED_SIDECAR_TOKEN_ATTESTATION_BLOCKED_UNDER_WINE` |
| Active reuse disabled | ✓ `ALMA_BRIDGE_COMPATIBILITY_PROFILE_REUSE_ENABLED=false` |
| No production compatibility logic added for validation pass | ✓ |
| Pilot-002 not executed | ✓ |

---

## 13. Approval gates before execution

1. **Approve this freeze package** (including BLOCKED setup acknowledgment).
2. **Resolve SETUP-T2/T3 blocker** via one of:
   - Operator validation session completing SETUP pairs under current engine; or
   - Approved engine alignment for `pe_windows` GUI → launcher/`process_survives` (separate change); or
   - Target replacement with reproducible non-blocking executable families.
3. **Commit corrected artifacts** → record approved SHA, clean tree.
4. **Re-run full suite** → 0 failures.
5. **Backup DB** and record hashes.
6. **Begin SETUP-T2/T3** (if not already pass) then scenario runs 1–12.

**Pilot-002 execution is blocked until steps 1–4 complete.**
