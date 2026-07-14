# Pilot-003 Execution Commands

**Campaign:** `shadow-validation-pilot-003`  
**Status:** Frozen — do not execute until explicitly approved.

All Wine runs clone a disposable prefix from an approved source snapshot. Never execute against `snapshots/` paths directly.

```bash
export REPO=/home/joshua/Desktop/Alma/alma-bridge
export PILOT003_ROOT="$HOME/.local/share/alma-bridge/prefixes/validation/pilot-003"
export ALMA_BRIDGE_VALIDATION_CAMPAIGN_MODE=true
export ALMA_BRIDGE_VALIDATION_CAMPAIGN_ID=shadow-validation-pilot-003
export ALMA_BRIDGE_VALIDATION_CAMPAIGN_DISPOSABLE_ROOT="$PILOT003_ROOT"
export ALMA_BRIDGE_VALIDATION_CAMPAIGN_SOURCE_SNAPSHOT="$PILOT003_ROOT/snapshots"
export ALMA_BRIDGE_COMPATIBILITY_PROFILE_REUSE_ENABLED=false
```

## run-01 — A_stable_repeat_success (T2)

Clone `source-t2-notepad64-*` → `runs/run-01-A-t2/`. Execute `notepad.exe`. Register `A_stable_repeat_success`.

## run-02 — B_relocated_executable (T2)

Clone T2 snapshot → `runs/run-02-B-t2/`. Copy `notepad.exe` to relocated path (same hash). Register `B_relocated_executable`.

## run-03 — C_compatible_host_drift (T2)

Clone T2 snapshot → `runs/run-03-C-t2/`. Label compatible host metadata drift. Register `C_compatible_host_drift`.

## run-04 — D_incompatible_host_drift (T2)

Clone T2 snapshot → `runs/run-04-D-t2/`. Apply shadow host overlay `host_arch=aarch64` at labeling/evaluation time. Expect `HOST_ARCH_MISMATCH`. Register `D_incompatible_host_drift`.

## run-05 — D_incompatible_host_drift (T3-arch notepad32)

Clone `source-t3-notepad32-*` → `runs/run-05-D-notepad32/`. Execute `syswow64/notepad.exe`. Shadow overlay `host_arch=aarch64`. Expect `HOST_ARCH_MISMATCH` against profile `9c96be17-46eb-46d7-ba0b-9c404f97bf80`. Register second `D_incompatible_host_drift`.

## run-06 — E_prefix_drift_windows (T2)

Clone T2 snapshot → `runs/run-06-E-windows-t2/`. Mutate `windows_version` only in disposable clone. Verified Bridge run. Register `E_prefix_drift_windows`.

## run-07 — E_prefix_drift_component (T2)

Clone T2 snapshot → `runs/run-07-E-component-t2/`. Remove installed component in disposable clone. Register `E_prefix_drift_component`.

## run-08 — F_clean_prefix_reconstruction (T2)

Fresh `wineboot -i` at `runs/run-08-F-t2/`. Shadow-only reconstruction prediction; reuse disabled. Register `F_clean_prefix_reconstruction`.

## run-09 — G_known_compatibility_failure (T3 WordPad)

Clone T3 wordpad snapshot → `runs/run-09-G-t3/`. Induce bounded compatibility failure. Register `G_known_compatibility_failure`.

## run-10 — H_unrelated_runtime_failure (T1 native)

Execute `scripts/validation/native_timeout_probe.sh` from temp cwd. Register `H_unrelated_runtime_failure`.

## run-11 — I_trust_state_imported (T2)

DB fixture: set imported trust on fixture profile. Shadow observe only. Register `I_trust_state_imported`.

## run-12 — I_trust_state_invalidated (T2)

Scoped invalidation on fixture profile. Register `I_trust_state_invalidated`.

## run-13 — J_multiple_candidate_ranking (T2)

**BLOCKED_PRECONDITION** until canonical query returns ≥2 eligible T2 candidates with distinct `bridge_manifest_hash`. Clone T2 snapshot → `runs/run-13-J-t2/`. Register `J_multiple_candidate_ranking`.
