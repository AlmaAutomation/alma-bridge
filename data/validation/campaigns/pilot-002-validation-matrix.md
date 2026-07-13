# Pilot-002 Validation Matrix — General Compatibility Profile Validation

**Status:** Preparation only — **do not execute** until explicitly approved.  
**Strategy:** Workstream A (general profiles) proceeds independently of Ascension (Workstream B).  
**Freeze commit (prep):** `982cf76`  
**Full suite at prep:** 545 passed, 0 failed (2026-07-13)

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
| **Canonical identity** | SHA-256 of script bytes at campaign freeze |
| **Verification contract** | Phase `native`; required check `exit_code_zero`; policy `bridge_aggregate_v1` |
| **program_kind** | `native_script` |
| **application_family** | `alma_validation_native` |
| **Disposable strategy** | No Wine prefix; run from two independent temp working directories |
| **Expected profile** | `locally_verified` after two successful Bridge runs; fingerprint stable across paths for scenario B |

### T2 — Wine 64-bit GUI (`wine-notepad64`)

| Field | Value |
|-------|-------|
| **Why appropriate** | Builtin PE32+ GUI; no proprietary sidecar/token IPC; `process_survives` verification via GUI detach |
| **Canonical path** | `{disposable_prefix}/drive_c/windows/system32/notepad.exe` after `wineboot -i` |
| **Canonical identity** | SHA-256 of `notepad.exe` bytes in disposable prefix at freeze (record at prep — reference `108168df…` on wine-9.0 Ubuntu) |
| **Verification contract** | Phase `launcher`; required `process_survives`; optional `log_excludes_signature`; GUI detach after survival window |
| **program_kind** | `windows_gui` |
| **application_family** | `wine_builtin_notepad64` |
| **Disposable strategy** | Fresh prefix per seed run under `prefixes/validation/pilot-002/` |
| **Expected profile** | `locally_verified` with `wine_prefix` binding; seeds scenarios C, D, E, F, I, J |

### T3 — Wine 32-bit GUI (`wine-notepad32`)

| Field | Value |
|-------|-------|
| **Why appropriate** | Distinct PE32 architecture (`syswow64`); same verification contract as T2 but different `executable_format`/architecture fingerprint |
| **Canonical path** | `{disposable_prefix}/drive_c/windows/syswow64/notepad.exe` |
| **Canonical identity** | SHA-256 of 32-bit `notepad.exe` at freeze |
| **Verification contract** | Phase `launcher`; required `process_survives` |
| **program_kind** | `windows_gui_pe32` |
| **application_family** | `wine_builtin_notepad32` |
| **Disposable strategy** | Independent disposable prefixes; never share inode with T2 primary seed prefix |
| **Expected profile** | Separate `locally_verified` profile; satisfies `min_program_kinds: 3` with T1+T2 |

---

## Scenario coverage matrix

| # | Scenario ID | Category | Target | Purpose |
|---|-------------|----------|--------|---------|
| 1 | `A_stable_repeat_success` | Stable repeat | T1 | First verified success + profile promotion |
| 2 | `A_stable_repeat_success` | Stable repeat | T1 | Second disposable env; same hash, new cwd |
| 3 | `B_relocated_executable` | Relocated path | T2 | Copy/symlink `notepad.exe` path; hash unchanged |
| 4 | `C_compatible_host_drift` | Compatible host drift | T2 | Simulated patch-level host metadata drift |
| 5 | `D_incompatible_host_drift` | Incompatible host | T2 | Wine major/capability rejection (negative) |
| 6 | `D_incompatible_host_drift` | Incompatible host | T3 | PE32 on simulated arch/capability mismatch |
| 7 | `E_prefix_drift_windows` | Bridge/prefix drift | T2 | `user.reg` Windows version drift |
| 8 | `E_prefix_drift_component` | Bridge/prefix drift | T3 | Remove optional winetricks component |
| 9 | `F_clean_prefix_reconstruction` | Prefix reconstruction | T2 | Fresh empty prefix + existing profile manifest |
| 10 | `G_known_compatibility_failure` | Known compat failure | T3 | Remove VC++/component; expect remediation then bounded fail or recover |
| 11 | `H_unrelated_runtime_failure` | Unrelated runtime | T1 | `native_timeout_probe.sh` exit 124 — not compatibility |
| 12 | `J_multiple_candidate_ranking` | Multi-candidate | T2 | Two eligible profile revisions; rank winner |

**Also exercised via setup of runs 1–12:**

| Scenario | How covered |
|----------|-------------|
| `I_trust_state_imported` | Seed imported profile on T2 before run 12 shadow compare |
| `I_trust_state_invalidated` | Invalidate seeded profile; expect diagnostic-only rejection |
| Bridge drift | Runs 7–8 (prefix/wine manifest drift vs profile manifest) |

---

## Ascension-blocked / deferred scenarios

These **do not** appear in Pilot-002 runs 1–12:

| Deferred item | Reason |
|---------------|--------|
| Nested Ascension C7 baseline | `ASCENSION_NESTED_SIDECAR_TOKEN_ATTESTATION_BLOCKED_UNDER_WINE` |
| Ascension Baseline A/B repeat | Requires C7 `VERIFYING → SUCCEEDED` first |
| Ascension `A_stable_repeat_success` | No reproducible verified success |
| Ascension `B_relocated_executable` | Blocked on verified seed profile |
| Any Ascension `locally_verified` promotion | Explicitly forbidden until research conditions met |
| `ascension-setup.exe` install path as profile seed | Installer/sidecar coupling; deferred to Workstream B |

Ascension evidence preserved under `data/validation/evidence/ascension-baseline/`.

---

## Per-run acceptance gates (all Workstream A runs)

Each profile-seeding run (1, 3, 10 seed phase) must produce:

- `BridgeOrchestrator` normal path (no manual bypass)
- `VerificationResult` persisted with `passed=true`
- `VERIFYING → SUCCEEDED` lifecycle
- `ProfileCandidateSnapshot` persisted
- `locally_verified` profile promotion
- `ShadowActualOutcome` + comparison recorded
- Primary/source Ascension prefixes **unchanged** (hash check in `prefix_guard.sh`)

Second success on T1/T2/T3 requires independent disposable environment or justified profile revision only.

---

## Disposable environment layout

```
~/.local/share/alma-bridge/prefixes/validation/pilot-002/
  seeds/
    t1-native/
    t2-notepad64/
    t3-notepad32/
  runs/
    run-01-A-t1/
    run-02-A-t1/
    …
  snapshots/   # optional DB/outcomes backup at freeze
```

Campaign env:

```bash
export ALMA_BRIDGE_VALIDATION_CAMPAIGN_MODE=true
export ALMA_BRIDGE_VALIDATION_CAMPAIGN_ID=shadow-validation-pilot-002
export ALMA_BRIDGE_VALIDATION_CAMPAIGN_DISPOSABLE_ROOT="$HOME/.local/share/alma-bridge/prefixes/validation/pilot-002"
export ALMA_BRIDGE_VALIDATION_CAMPAIGN_PRIMARY_PREFIX="<operator primary — guard only, not execution>"
export ALMA_BRIDGE_VALIDATION_CAMPAIGN_SOURCE_SNAPSHOT="<not used for T1/T2/T3; Ascension snapshot forbidden as run target>"
```

---

## Promotion gate alignment (unchanged thresholds)

From `PromotionGateThresholds`:

- `min_program_kinds: 3` — satisfied by T1, T2, T3
- `min_scenario_categories: 5` — matrix spans A, B, C, D, E, F, G, H, I, J
- Precision/rejection/drift rates — computed from labeled shadow comparisons only

---

## Execution checklist (operator, post-approval)

1. Confirm `git` HEAD matches approved freeze SHA and working tree clean.
2. Run full suite — zero failures required.
3. Record canonical SHA-256 for T1 script, T2/T3 notepad at freeze.
4. Backup `outcomes.db` to `data/validation/backups/`.
5. Execute runs 1–12 in order; register each via `alma_bridge.cli.shadow_validation`.
6. Label shadow comparisons per manifest.
7. Generate promotion gate report; do not conflate with Pilot-001 or Ascension research.

**Pilot-002 execution remains blocked until explicit approval.**
