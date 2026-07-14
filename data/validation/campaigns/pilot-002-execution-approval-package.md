# Pilot-002 Workstream A — Final Execution Approval Package

**Date:** 2026-07-14  
**Status:** `ready_for_execution_approval` — **DO NOT EXECUTE Pilot-002 scenario runs until explicitly approved**  
**Freeze commit:** `5aa826eb1334823e9bf4f96088ecdc6b3d6bdeea`  
**Git tree SHA:** `918682920aaca5b0704039eceef6d5924ecf0efe`  
**Working tree:** clean at freeze commit  

---

## 1. Freeze commit

| Item | Value |
|------|-------|
| Commit SHA | `5aa826eb1334823e9bf4f96088ecdc6b3d6bdeea` |
| Tree SHA | `918682920aaca5b0704039eceef6d5924ecf0efe` |
| Message | `feat: add verified Wine GUI execution contract` |
| Branch | `master` |
| Working tree | **clean** (verified post-commit) |
| Staged secret scan | **SECRET_SCAN_CLEAN** |
| Runtime DBs / `.env` / backups / evidence / logs | **gitignored** (`data/*`, `.env`, `data/validation/backups/`) |
| Disposable prefixes | **outside repo** (`~/.local/share/alma-bridge/prefixes/`) |
| Active reuse implementation | **absent** — `compatibility_profile_reuse_enabled` logged only; no reuse execution branch |

---

## 2. Authoritative baseline (from freeze commit `5aa826e`)

| Suite | Command | Result | Runtime |
|-------|---------|--------|---------|
| **Full suite** | `cd /home/joshua/Desktop/Alma/alma-bridge && . .venv/bin/activate && export PYTHONPATH=/home/joshua/Desktop/Alma/alma-bridge && pytest -q` | **561 passed, 0 failed** | **1086 s** (~18:06) UTC `2026-07-14T00:06:08Z` → `00:24:14Z` |
| **Architecture invariant** | `pytest -q tests/test_profile_shadow.py::test_run_f_profile_reconstruction_blocked_when_reuse_disabled` | **1 passed** | included below |
| **Focused Wine GUI + shadow** | `pytest -q tests/test_profile_shadow.py::test_run_f_profile_reconstruction_blocked_when_reuse_disabled tests/test_wine_gui_contract.py` | **15 passed, 0 failed** | **16 s** |

Pre-commit results are **not** reused as the campaign freeze baseline.

---

## 3. Setup profile identity / idempotency analysis

### Root cause (pre-fix defect)

| Field | Classification |
|-------|----------------|
| Defect ID | `WINEPREFIX_MANIFEST_IDENTITY_LEAK` |
| Mechanism | `WINEPREFIX` disposable path was included in `bridge_manifest.environment` |
| Idempotency impact | `idempotency_key = hash(lineage + manifest_hash + verification_binding)` diverged per prefix path |
| Symptom | SETUP-T2-A/B and SETUP-T3-A/B created **separate profile revisions** (rev 1 + rev 2) instead of attachment |

**Manifest diff (pre-fix T2-A vs T2-B):** only `environment.WINEPREFIX` differed (`t2-notepad64-a` vs `t2-notepad64-b`). No material bridge-family, host-class, verification-binding, or remediation difference.

### Fix (in freeze commit)

- `_stable_env()` excludes `WINEPREFIX` and `WINEDEBUG` from manifest identity (prefix path is audit-only per design §Prefix reference).
- Regression test: `tests/test_profile_fingerprints.py::test_wineprefix_path_does_not_change_manifest_identity`

### Post-fix setup rerun (2026-07-14)

| Setup | Promotion | Profile ID | Revision | Same manifest as pair? |
|-------|-----------|------------|----------|------------------------|
| SETUP-T2-A | `created` | `a5576257-65b5-485f-a966-8273bccd8146` | 3 | — |
| SETUP-T2-B | **`attached`** | `a5576257-65b5-485f-a966-8273bccd8146` | 3 | ✓ `0ae990e9…` |
| SETUP-T3-A | `created` | `281e69a0-e3e8-46cc-8de5-2639facce95f` | 3 | — |
| SETUP-T3-B | **`attached`** | `281e69a0-e3e8-46cc-8de5-2639facce95f` | 3 | ✓ `0ae990e9…` |

**Canonical T2 profile:** `a5576257-65b5-485f-a966-8273bccd8146` (rev 3, 2 verification attachments)  
**Canonical T3 profile:** `281e69a0-e3e8-46cc-8de5-2639facce95f` (rev 3, 2 verification attachments)

**Legacy defective rows retained (not deleted):** `425f8664` (T2 rev1), `bebf5c5f` (T2 rev2), `6aec0dd2` (T3 rev1), `9b0cf7ff` (T3 rev2) — prefix-path manifest leak artifacts.

### Identity field comparison (canonical post-fix pair)

| Field | T2-A / T2-B | T3-A / T3-B |
|-------|-------------|-------------|
| `program_identity_key` | identical within pair | identical within pair |
| `host_compatibility_class_id` | identical | identical |
| `bridge_family_key` | identical (`77ae04f2…`) | identical |
| `bridge_manifest_hash` | **identical** (post-fix) | **identical** (post-fix) |
| `verification_binding_key` | identical | identical |
| `profile_lineage_key` | identical within pair | identical within pair |
| `profile_revision` | 3 (single row) | 3 (single row) |
| `idempotency_key` | **identical** (B attaches) | **identical** (B attaches) |

---

## 4. Wine GUI success contract — setup process evidence

All four post-fix setup runs: phase `wine_gui`, policy `wine_gui_process_v1`, checks `process_survives` + `target_process_identity`, `VERIFYING → SUCCEEDED`.

| Setup | Session | Target basename | Startup | Survival | PID cmdline | Infra excluded |
|-------|---------|-----------------|---------|----------|-------------|----------------|
| SETUP-T2-A | `946b3255…` | `notepad.exe` | 0.008 s | 3.0 s | `C:\windows\system32\notepad.exe` | wineserver/explorer not credited |
| SETUP-T2-B | `e05fa30f…` | `notepad.exe` | 0.009 s | 3.0 s | `C:\windows\system32\notepad.exe` | same |
| SETUP-T3-A | `c286a9da…` | `wordpad.exe` | 0.009 s | 3.0 s | `C:\Program Files\Windows NT\Accessories\wordpad.exe` | same |
| SETUP-T3-B | `a825d779…` | `wordpad.exe` | 0.011 s | 3.0 s | `C:\Program Files\Windows NT\Accessories\wordpad.exe` | same |

**Lifecycle ordering confirmed:** VerificationResult persisted (`verification_passed=true`) → ProfileCandidateSnapshot → promotion (`created`/`attached`) → campaign-owned GUI processes cleaned after evidence capture (`handoff_contract=wine_gui_process_v1`).

---

## 5. Revised 12-run matrix

Setup-generated mutable prefixes (`ascension-baseline/setup/*`) are **not** reused as scenario sources. Use **source snapshots** (§8) or fresh `wineboot -i` per run.

| # | Scenario | Target | Prerequisites | Shadow eligibility | Expected rejection | Drift dimensions | Verification | Label guidance | Disposable env | Cleanup |
|---|----------|--------|---------------|-------------------|-------------------|------------------|--------------|----------------|----------------|---------|
| 1 | `A_stable_repeat_success` | T2 notepad64 | Canonical T2 profile; fresh prefix | eligible | — | — | `wine_gui_process_v1`; repeat success | high | `pilot-002/runs/run-01-A-t2/` | kill GUI PIDs; rm prefix |
| 2 | `B_relocated_executable` | T2 copy | Canonical T2; copy exe new path same hash | eligible | — | — | same hash, new path alias | high | `run-02-B-t2/` | rm copy + prefix |
| 3 | `C_compatible_host_drift` | T2 | Canonical T2; simulated patch-level host metadata | eligible | — | `host_class` (minor) | success; reduced env confidence | medium | `run-03-C-t2/` | restore host snapshot |
| 4 | `D_incompatible_host_drift` | T2 | Canonical T2; simulate Wine major/capability mismatch | **ineligible** | `HOST_CLASS_MISMATCH` / capability | `host_class` | fail or shadow reject | high | `run-04-D-t2/` | restore metadata |
| 5 | `D_incompatible_host_drift` | T3-arch notepad32 | win64 host + PE32 target | **ineligible** | arch/capability | `host_class`, arch | rejection expected | high | `run-05-D-notepad32/` | rm prefix |
| 6 | `E_prefix_drift` | T2 | Canonical T2; **combined** `windows_version` + `installed_components` drift | eligible w/ drift flags | possible scoped invalidation | `windows_version`, `installed_components` | verified or bounded fail | medium | `run-06-E-t2/` | restore components |
| 7 | `F_clean_prefix_reconstruction` | T2 | Canonical T2 manifest; **fresh** prefix only | shadow predicts `reconstruction_required` | — | `PREFIX_UNAVAILABLE` | shadow-only; **no prefix mutation** | high | `run-07-F-t2/` | rm prefix |
| 8 | `G_known_compatibility_failure` | T3-arch or T3 WordPad | Remove VC++/component | ineligible or fail | missing component | `installed_components` | bounded compat fail | high | `run-08-G/` | restore component |
| 9 | `H_unrelated_runtime_failure` | T1 `native_timeout_probe.sh` | None | N/A (native) | — | — | exit 124 unrelated | high | temp cwd | none |
| 10 | `I_trust_state_imported` | T2 | Inject/import profile row `trust_state=imported` | shadow observe only | `IMPORTED_NOT_ELIGIBLE` | trust | no active reuse | high | DB label only | revert import fixture |
| 11 | `I_trust_state_invalidated` | T2 | Invalidate canonical or fixture profile | ineligible | invalidation scope | trust/lifecycle | diagnostic reject | high | DB label only | clear invalidation |
| 12 | `J_multiple_candidate_ranking` | T2 | **Precondition query passes** (§6) | rank ≥2 eligible | — | manifest/family divergence | ranking only; no fabrication | medium | `run-12-J-t2/` | per ranked attempt |

### Run F shadow-only invariant

- `ALMA_BRIDGE_COMPATIBILITY_PROFILE_REUSE_ENABLED=false` enforced
- No `run_prefix_mutation` from profile replay
- `ProfileShadowService` predicts; planner + orchestrator run independently
- Test: `tests/test_profile_shadow.py::test_run_f_profile_reconstruction_blocked_when_reuse_disabled` — **passing**

---

## 6. Run J precondition

### Query at freeze (all `locally_verified` T2 rows — includes legacy defective)

```sql
WITH eligible AS (
  SELECT p.profile_id, p.trust_state, p.lifecycle_state, p.bridge_family_key,
         p.bridge_manifest_hash, p.profile_revision, pf.executable_hash
  FROM compatibility_profiles p
  JOIN compatibility_profile_program_fingerprints pf ON pf.profile_id = p.profile_id
  WHERE pf.executable_hash = '108168df2b9679c5ef4004a5fa63990c99b189661ee3cac4bb8f9dd467ad6d69'
    AND p.trust_state = 'locally_verified'
    AND p.lifecycle_state IN ('ACTIVE', 'VERIFIED')
)
SELECT COUNT(*) AS eligible_count,
       COUNT(DISTINCT bridge_manifest_hash) AS distinct_manifests,
       COUNT(DISTINCT bridge_family_key) AS distinct_families,
       COUNT(DISTINCT profile_revision) AS distinct_revisions
FROM eligible;
```

**Freeze-time result:** `eligible_count=3`, `distinct_manifests=3`, `distinct_families=1`, `distinct_revisions=3`  
(Legacy rev1/rev2 from `WINEPREFIX_MANIFEST_IDENTITY_LEAK` inflate counts.)

### Canonical-only query (recommended before Run 12)

```sql
SELECT p.profile_id, p.profile_revision, p.bridge_manifest_hash, p.trust_state, p.lifecycle_state
FROM compatibility_profiles p
JOIN compatibility_profile_program_fingerprints pf ON pf.profile_id = p.profile_id
WHERE pf.executable_hash = '108168df2b9679c5ef4004a5fa63990c99b189661ee3cac4bb8f9dd467ad6d69'
  AND p.profile_id = 'a5576257-65b5-485f-a966-8273bccd8146'
  AND p.trust_state = 'locally_verified'
  AND p.lifecycle_state IN ('ACTIVE', 'VERIFIED');
```

**Result:** 1 canonical candidate at freeze.

### Second candidate generation plan (no fabrication)

1. **Run 6 (`E_prefix_drift`)** on fresh disposable prefix: apply material `windows_version` and/or `installed_components` change via bounded remediation/winetricks; complete verified Bridge run → promotes **new revision** (same lineage, different `bridge_manifest_hash`).
2. **Before Run 12:** re-run canonical-only precondition extended query requiring `distinct_manifests >= 2` where both profiles trace to post-freeze verified Bridge runs (exclude legacy IDs `425f8664`, `bebf5c5f`, `425f8664-7ddd-4a99-b984-435051027e8f` lineage rev ≤2 unless explicitly re-verified).
3. Ranking components: manifest hash divergence + shared program identity + same bridge family.

Setup runs **do not** count as scenario evidence for Run J.

---

## 7. Campaign freeze artifacts

| Artifact | Location / value |
|----------|------------------|
| DB backup | `data/validation/backups/outcomes.db.pilot-002-freeze.20260714T000425Z` |
| DB backup SHA-256 | `3615fd6635843e1efe001c45d93ad4ac85b5c0890d69889bfa41a643792f806e` |
| T2 source snapshot | `~/.local/share/alma-bridge/prefixes/validation/pilot-002/snapshots/source-t2-notepad64-20260714T000425Z` |
| T2 snapshot aggregate hash | `ee165aaa13c103d51067457bf5490786cc93a46ffab007c37ffdcf7b72605f00` |
| T3 source snapshot | `~/.local/share/alma-bridge/prefixes/validation/pilot-002/snapshots/source-t3-wordpad64-20260714T000425Z` |
| T3 snapshot aggregate hash | `2ef515d4cbf69a008d8358e0923bccef0f4dc9c5130aa2049a15f314b7308252` |
| Setup mutable prefixes | **not** approved as scenario sources |

### Target executable hashes

| Target | SHA-256 |
|--------|---------|
| T1 `native_success_probe.sh` | `9c9c8180e7ab13b2ca48c2c9750bb16ce32eeeb017afbec31320cc22f4cb2b00` |
| T2 notepad64 | `108168df2b9679c5ef4004a5fa63990c99b189661ee3cac4bb8f9dd467ad6d69` |
| T3 wordpad64 | `a2bddbb8d43eb96b750813ab8f30db847d2b60d2838dd5fcb36348a719157266` |
| T3-arch notepad32 | `503665cbf1e3be907387c2b76beb25bcdef7d326738adf6f06ff53b9984a2684` |

### Runtime versions

| Component | Value |
|-----------|-------|
| Wine | `wine-9.0 (Ubuntu 9.0~repack-4build3)` |
| Verification policy | `bridge_aggregate_v1` / `1.0.0` |
| Wine GUI policy | `wine_gui_process_v1` |
| Fingerprint schema | `fingerprint_schema_v1` |
| Shadow eval | `shadow_eval_v1` |
| Ranking | `profile_shadow_rank_v1` / `1.0.0` |

### Campaign input hashes (at freeze commit `5aa826e`)

| Input | SHA-256 |
|-------|---------|
| `shadow-validation-pilot-002.json` | `90b96fe67383fec1c3bea26da5aa74a3a8434519b76a76879bf55ad276196f9a` |
| `pilot-002-validation-matrix.md` | `1dcfaa14017b72a21fc9b94d8e39afbbf2d5d0ed30eea94b6f65c9d5e4fbef05` |
| `pilot-002-freeze-package.md` | `d088144d597f7296673333da2bfed4869e1189eacb805a584e0d4f6d7b07e5af` |
| `shadow_scenario_manifest_v1.json` | `8a0f95a46ccadd57665f0a24e6b6eeb4fd8d6c6a17a3d97aa9ce6a10f4dabf28` |
| Git commit | `5aa826eb1334823e9bf4f96088ecdc6b3d6bdeea` |
| Git tree | `918682920aaca5b0704039eceef6d5924ecf0efe` |
| DB backup | `3615fd6635843e1efe001c45d93ad4ac85b5c0890d69889bfa41a643792f806e` |
| T2 source snapshot | `ee165aaa13c103d51067457bf5490786cc93a46ffab007c37ffdcf7b72605f00` |
| T3 source snapshot | `2ef515d4cbf69a008d8358e0923bccef0f4dc9c5130aa2049a15f314b7308252` |

**Campaign status:** `ready_for_execution_approval` (not `in_progress`)

---

## 8. Required feature flags (frozen)

```
ALMA_BRIDGE_COMPATIBILITY_PROFILES_ENABLED=true
ALMA_BRIDGE_COMPATIBILITY_PROFILE_CREATION_ENABLED=true
ALMA_BRIDGE_COMPATIBILITY_PROFILE_SHADOW_MODE=true
ALMA_BRIDGE_COMPATIBILITY_PROFILE_REUSE_ENABLED=false
ALMA_BRIDGE_OPERATOR_ENABLED=false
ALMA_BRIDGE_OPERATOR_ALLOW_MUTATIONS=false
ALMA_BRIDGE_VALIDATION_CAMPAIGN_MODE=true
ALMA_BRIDGE_VALIDATION_CAMPAIGN_ID=shadow-validation-pilot-002
```

---

## 9. Confirmations

| Confirmation | Status |
|--------------|--------|
| Pilot-001 evidence excluded from gate calculations | ✓ `exclude_from_gate_calculations` |
| Ascension research-only (Workstream B) | ✓ `ASCENSION_NESTED_SIDECAR_TOKEN_ATTESTATION_BLOCKED_UNDER_WINE` |
| Active reuse disabled | ✓ flag false; Run F invariant passing |
| No active-reuse implementation in orchestrator | ✓ logging only |
| Pilot-002 scenario runs not executed | ✓ |
| Wine GUI contract completion gate | ✓ approved and implemented |
| WINEPREFIX idempotency defect fixed + regression test | ✓ |

---

## 10. Approval gate

**Pilot-002 scenario execution remains BLOCKED** until operator explicitly approves this package.

Post-approval sequence:
1. Confirm Git SHA `5aa826e` and input hashes match.
2. Restore DB from backup if needed.
3. Execute setup verification (already PASS) — do not mix into scenario metrics.
4. Runs 1–11 per matrix.
5. Complete Run 6 → verify Run J precondition (≥2 canonical candidates).
6. Run 12 only if precondition passes.
