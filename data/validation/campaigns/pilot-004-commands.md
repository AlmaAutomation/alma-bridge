# Pilot-004 Execution Commands (DRAFT — NOT APPROVED)

**Campaign:** `shadow-validation-pilot-004`

All Wine runs clone a disposable prefix from an approved source snapshot. Never execute against `snapshots/` paths directly.

```bash
export REPO=/home/joshua/Desktop/Alma/alma-bridge
export PILOT004_ROOT="$HOME/.local/share/alma-bridge/prefixes/validation/pilot-004"
export ALMA_BRIDGE_VALIDATION_CAMPAIGN_MODE=true
export ALMA_BRIDGE_VALIDATION_CAMPAIGN_ID=shadow-validation-pilot-004
export ALMA_BRIDGE_VALIDATION_CAMPAIGN_DISPOSABLE_ROOT="$PILOT004_ROOT"
export ALMA_BRIDGE_VALIDATION_CAMPAIGN_SOURCE_SNAPSHOT="$PILOT004_ROOT/snapshots"
export ALMA_BRIDGE_COMPATIBILITY_PROFILE_REUSE_ENABLED=false
```

## run-01 — A_stable_repeat_success

Clone T2 snapshot → `runs/run-01-A-t2/`. Register `A_stable_repeat_success`. Label: `winner_correct`.

## run-02 — B_relocated_executable

Clone T2 snapshot → `runs/run-02-B-t2/`. Copy `notepad.exe` to relocated path (same hash). Register `B_relocated_executable`.

## run-03 — C_compatible_host_drift

Clone T2 snapshot → `runs/run-03-C-t2/`. Pass `shadow_host_payload_overlay: {"os_family":"ubuntu"}` on BridgeRequest **before** planning. Register `C_compatible_host_drift`.

## run-04 — D_incompatible_host_drift (T2)

Clone T2 snapshot. Pass `shadow_host_payload_overlay: {"host_arch":"aarch64"}` on BridgeRequest **before** planning. Expect immutable `HOST_ARCH_MISMATCH` on canonical profile. Label: `rejected_correct`.

## run-05 — D_incompatible_host_drift (notepad32)

Clone notepad32 snapshot. Same pre-plan overlay. Expect rejection on arch profile. Label: `rejected_correct`.

## run-06 — E_prefix_drift_windows

Clone → record baseline winver → `set_wine_windows_version(prefix, "win7")` → read back win7 → Bridge run (shadow before repair). Expect `WINDOWS_VERSION_DRIFT` in immutable candidate. Label: `drift_correct`.

## run-07 — E_prefix_drift_component

Clone **corefonts snapshot** → record baseline → remove `corefonts` marker files → read back absence → Bridge run. Expect `COMPONENT_MISSING`. Label: `drift_correct`.

## run-08 — F_clean_prefix_reconstruction

Fresh `wineboot -i` at `runs/run-08-F-t2/`. Shadow-only reconstruction prediction; reuse disabled. Register `F_clean_prefix_reconstruction`. Label: `drift_correct`.

## run-09 — G_known_compatibility_failure

Clone T2 snapshot → **delete** `drive_c/windows/system32/notepad.exe` from disposable clone only → Bridge run. Expect failure. Label: `indeterminate`.

## run-10 — H_unrelated_runtime_failure

Execute `scripts/validation/native_timeout_probe.sh` from temp cwd. Register `H_unrelated_runtime_failure`.

## run-11 — I_trust_state_imported

DB fixture: imported trust on `425f8664…`. Expect imported candidate `trust_category=shadow_observation_only`, `winner_selectable=false`. Label imported fixture: `rejected_correct` (NOT `shadow_observation_only`).

## run-12 — I_trust_state_invalidated

Invalidate `bebf5c5f…`. Label: `rejected_correct` with `INVALIDATED_PROFILE_DIAGNOSTIC_ONLY`.

## run-13 — J_multiple_candidate_ranking

Precondition query must return ≥2 eligible candidates with distinct manifests from SETUP-T2-A and SETUP-T2-B provenance.
