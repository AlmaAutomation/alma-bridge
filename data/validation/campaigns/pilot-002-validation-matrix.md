# Pilot-002 Validation Matrix — General Compatibility Profile Validation

**Status:** Corrected freeze package — **do not execute** until explicitly approved.  
**Strategy:** Workstream A (general profiles) proceeds independently of Ascension (Workstream B).  
**Prep baseline commit:** `0f91cae`  
**Corrected freeze:** see `data/validation/campaigns/pilot-002-freeze-package.md`

---

## Workstream split

| Workstream | Objective | Pilot-002 role |
|------------|-----------|----------------|
| **A — General** | Validate profile creation, shadow, drift, ranking, promotion on reproducible successes | **This matrix** |
| **B — Ascension research** | `ASCENSION_NESTED_SIDECAR_TOKEN_ATTESTATION_BLOCKED_UNDER_WINE` | Deferred; see `data/validation/research/ascension-nested-sidecar-token-attestation.md` |

Promotion thresholds unchanged. Pilot-001 evidence excluded. `ALMA_BRIDGE_COMPATIBILITY_PROFILE_REUSE_ENABLED=false` throughout.

---

## Target program selection (three classes)

### T1 — Native script (`native_success_probe`)

| Field | Value |
|-------|-------|
| **Why appropriate** | Reproducible `exit 0`; exercises native verification path (`exit_code_zero`) without Wine/sidecar complexity |
| **Canonical path** | `scripts/validation/native_success_probe.sh` (repo-relative, recorded at freeze SHA) |
| **Canonical identity (SHA-256)** | `9c9c8180e7ab13b2ca48c2c9750bb16ce32eeeb017afbec31320cc22f4cb2b00` |
| **Verification contract** | Phase `native`; required check `exit_code_zero`; policy `bridge_aggregate_v1` |
| **program_kind** | `native_script` |
| **application_family** | `alma_validation_native` |
| **Disposable strategy** | No Wine prefix; two independent temp working directories / DB roots |
| **Expected profile** | `locally_verified` after SETUP pair; second verified success attaches evidence or justified revision only |

**SETUP preflight (2026-07-13):** SETUP-T1-A and SETUP-T1-B both reached `VERIFYING → SUCCEEDED` via `BridgeOrchestrator` with `exit_code_zero`.

### T2 — Wine 64-bit Notepad (`wine-notepad64`)

| Field | Value |
|-------|-------|
| **Why appropriate** | Builtin PE32+ GUI; no proprietary sidecar/token IPC; seeds most Windows scenarios |
| **Canonical path** | `{disposable_prefix}/drive_c/windows/system32/notepad.exe` after `wineboot -i` |
| **Canonical identity (SHA-256)** | `108168df2b9679c5ef4004a5fa63990c99b189661ee3cac4bb8f9dd467ad6d69` |
| **Wine version at freeze** | `wine-9.0 (Ubuntu 9.0~repack-4build3)` |
| **Prefix architecture** | `win64` (PE32+ in `system32`) |
| **Verification contract (campaign)** | Phase `launcher`; required `process_survives`; `wine_has_main_launcher_process` must match `system32/notepad.exe`, not generic wineserver |
| **program_kind** | `pe_windows` |
| **application_family** | `wine_builtin_notepad64` |
| **Disposable strategy** | Fresh prefix per run under `prefixes/validation/pilot-002/`; no shared mutable prefix between SETUP-T2-A and SETUP-T2-B |
| **Expected profile** | `locally_verified` with `wine_prefix` binding |

**SETUP status:** BLOCKED at freeze — see freeze package §3 (engine contract gap for blocking `pe_windows` GUI).

### T3 — Wine 64-bit WordPad (`wine-wordpad64`) — distinct application family

| Field | Value |
|-------|-------|
| **Why appropriate** | Distinct Windows accessory family from Notepad; builtin PE32+ GUI; no proprietary IPC/attestation; deterministic executable identity |
| **Source / provenance** | Wine builtin from `wineboot -i` disposable prefix (`drive_c/Program Files/Windows NT/Accessories/wordpad.exe`); Microsoft Windows accessory redistributable via Wine; validation use only |
| **Canonical path** | `{disposable_prefix}/drive_c/Program Files/Windows NT/Accessories/wordpad.exe` |
| **Canonical identity (SHA-256)** | `a2bddbb8d43eb96b750813ab8f30db847d2b60d2838dd5fcb36348a719157266` |
| **Architecture** | PE32+ x86-64 GUI |
| **License / use suitability** | Wine ships accessory binaries for prefix initialization; no proprietary launcher attestation; suitable for isolated validation prefixes |
| **Verification contract (campaign)** | Phase `launcher`; required `process_survives` (same launcher-PID contract as T2) |
| **program_kind** | `pe_windows` |
| **application_family** | `wine_builtin_wordpad64` |
| **Disposable strategy** | Independent disposable prefixes; never share inode with T2 seed prefixes |
| **Expected profile** | Separate `locally_verified` profile; satisfies `min_program_kinds: 3` with T1+T2 |

**SETUP status:** BLOCKED at freeze — two preflight Bridge runs not completed (blocking GUI + engine contract gap). Do not count SETUP-T3 in scenario metrics until pair succeeds.

### T3-arch — Wine 32-bit Notepad (`wine-notepad32`) — architecture / rejection only

| Field | Value |
|-------|-------|
| **Role** | **Not** the primary T3 diversity seed; used only for PE32 architecture and incompatible-rejection scenarios |
| **Canonical path** | `{disposable_prefix}/drive_c/windows/syswow64/notepad.exe` |
| **Canonical identity (SHA-256)** | `503665cbf1e3be907387c2b76beb25bcdef7d326738adf6f06ff53b9984a2684` |
| **Verification contract** | Phase `launcher`; required `process_survives` (campaign intent) |
| **application_family** | `wine_builtin_notepad32` |

---

## Setup runs (excluded from 12 scenario metrics)

Each pair establishes reproducibility before scenario testing. Failure → exclude target from scenario metrics; preserve evidence; do not change production logic during campaign.

| Setup ID | Target | Disposable env | Required outcomes |
|----------|--------|----------------|-------------------|
| SETUP-T1-A | T1 | Independent temp DB + cwd | `VERIFYING → SUCCEEDED`, VerificationResult, ProfileCandidateSnapshot, `locally_verified` |
| SETUP-T1-B | T1 | Independent temp DB + cwd | Same; second success attaches evidence or justified revision |
| SETUP-T2-A | T2 | Independent wine prefix A | Same |
| SETUP-T2-B | T2 | Independent wine prefix B | Same |
| SETUP-T3-A | T3 WordPad | Independent wine prefix A | Same |
| SETUP-T3-B | T3 WordPad | Independent wine prefix B | Same |

**At corrected freeze:** SETUP-T1-A/B **PASS**; SETUP-T2/T3 **BLOCKED** (documented in freeze package).

---

## Scenario coverage matrix (12 runs)

Setup pairs satisfy stable-repeat reproducibility per target. Scenario runs below are **in addition to** setup and excluded from the 12-count only for setup rows above.

| # | Scenario ID | Category | Target | Purpose |
|---|-------------|----------|--------|---------|
| 1 | `A_stable_repeat_success` | Stable repeat | T2 | Verified repeat on independent disposable prefix |
| 2 | `B_relocated_executable` | Relocated path | T2 | Copy/symlink `notepad.exe`; hash unchanged |
| 3 | `C_compatible_host_drift` | Compatible host drift | T2 | Simulated patch-level host metadata drift |
| 4 | `D_incompatible_host_drift` | Incompatible host | T2 | Wine major/capability rejection (negative) |
| 5 | `D_incompatible_host_drift` | Incompatible host | T3-arch (notepad32) | PE32 arch/capability mismatch rejection |
| 6 | `E_prefix_drift` | Bridge/prefix drift | T2 | **Combined category:** `windows_version` + `installed_components` drift dimensions in one run |
| 7 | `F_clean_prefix_reconstruction` | Prefix reconstruction (**shadow-only**) | T2 | See Run F semantics below |
| 8 | `G_known_compatibility_failure` | Known compat failure | T3-arch or T3 WordPad | Remove VC++/component; bounded fail or recover |
| 9 | `H_unrelated_runtime_failure` | Unrelated runtime | T1 | `native_timeout_probe.sh` exit 124 — not compatibility |
| 10 | `I_trust_state_imported` | Trust state | T2 | **Explicit** imported profile; shadow observation only |
| 11 | `I_trust_state_invalidated` | Trust state | T2 | **Explicit** invalidated profile; diagnostic-only rejection |
| 12 | `J_multiple_candidate_ranking` | Multi-candidate | T2 | Rank ≥2 eligible candidates; **blocked** if precondition query fails |

**Stable repeat (T1):** covered by SETUP-T1-A/B (excluded from 12 metrics). T1 does not consume a scenario slot.

**Full validation dataset note:** Prefix-drift full dataset retains ≥10 drift cases by splitting E windows/component across future runs; Pilot-002 combines both dimensions in run 6.

---

## Run F — `F_clean_prefix_reconstruction` (shadow-only)

| Requirement | Implementation |
|-------------|----------------|
| Verified profile manifest exists | From SETUP-T2 promoted profile for T2 executable identity |
| Fresh disposable prefix | `wineboot -i` under `pilot-002/runs/run-07-F/` |
| Shadow evaluates reconstruction eligibility | `ProfileShadowService.create_prediction` + drift `PREFIX_UNAVAILABLE` |
| **No prefix mutation** | `ALMA_BRIDGE_COMPATIBILITY_PROFILE_REUSE_ENABLED=false`; no `run_prefix_mutation` from profile replay |
| Normal planner + BridgeOrchestrator | Independent compatibility path; actual outcome recorded separately |
| Comparison | Labels whether shadow reconstruction prediction was correct (`reconstruction_required` metric only) |

Invariant test: `tests/test_profile_shadow.py::test_run_f_profile_reconstruction_blocked_when_reuse_disabled`

---

## Run J — multiple-candidate ranking precondition

Before run 12, execute read-only query in `pilot-002-freeze-package.md` §Run J. If fewer than two eligible candidates, different revisions/families, or either is imported/invalidated: **mark Run 12 BLOCKED**; do not fabricate candidates; do not count setup runs as scenario evidence.

---

## Ascension-blocked / deferred scenarios

| Deferred item | Reason |
|---------------|--------|
| Nested Ascension C7 baseline | `ASCENSION_NESTED_SIDECAR_TOKEN_ATTESTATION_BLOCKED_UNDER_WINE` |
| Ascension profile promotion | Research-only until Workstream B conditions met |
| Ascension as T1/T2/T3 seed | Forbidden |

---

## Per-run acceptance gates (Workstream A)

- `BridgeOrchestrator` normal path (no manual bypass)
- `VerificationResult` persisted with `passed=true` on success paths
- `VERIFYING → SUCCEEDED` lifecycle
- `ProfileCandidateSnapshot` persisted before success
- `locally_verified` profile promotion
- `ShadowActualOutcome` + comparison recorded
- Primary/source Ascension prefixes **unchanged** (`prefix_guard.sh`)

---

## Disposable environment layout

```
~/.local/share/alma-bridge/prefixes/validation/pilot-002/
  setup/
    t1-native/
    t2-notepad64-a/
    t2-notepad64-b/
    t3-wordpad64-a/
    t3-wordpad64-b/
  runs/
    run-01-A-t2/
    run-02-B-t2/
    …
  snapshots/
```

---

## Execution checklist (operator, post-approval)

1. Confirm freeze package approved and Git SHA matches.
2. Run full suite — zero failures required.
3. Complete BLOCKED setup pairs (T2, T3) or replace targets before scenario runs.
4. Backup `outcomes.db` to `data/validation/backups/`.
5. Execute setup (if not done) then runs 1–12; register via `alma-bridge-shadow-validation`.
6. Run J precondition query before run 12.
7. Label shadow comparisons per manifest.

**Pilot-002 execution remains blocked until explicit approval of the freeze package.**
