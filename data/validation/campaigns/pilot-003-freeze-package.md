# Pilot-003 Freeze Package

**Corrective commit:** `6bf06ca14e760a4f976279f1ee9fd201dffa2080`  
**Status:** `ready_for_execution_approval` — scenario execution **NOT APPROVED**

---

## Run 4 — incompatible host (deterministic)

| Field | Value |
|-------|-------|
| Target | T2 notepad64 (`108168df…`) |
| Candidate | Canonical T2 profile `a5576257-65b5-485f-a966-8273bccd8146` |
| Induced mismatch | Scenario shadow host overlay `host_arch: aarch64` vs stored profile `host_arch: x86_64` |
| Expected reason | `HOST_ARCH_MISMATCH` |
| Physical host | Unchanged |
| Bridge execution | May succeed independently |

Freeze audit case `run4_T2_candidate_host_arch_mismatch`: **rejected** with `HOST_ARCH_MISMATCH`.

Alternate documented path: `required_capabilities: ["validation_scenario_gpu_cuda"]` → `REQUIRED_CAPABILITY_MISSING` (audit case `run4_required_capability_missing`).

## Run 5 — architecture variant (deterministic)

| Field | Value |
|-------|-------|
| Objective | Architecture host-class mismatch **with existing candidate** |
| Executable | PE32 notepad32 (`503665cb…`) |
| Profile | `9c96be17-46eb-46d7-ba0b-9c404f97bf80` (SETUP-T3-arch-A) |
| Induced mismatch | Shadow host overlay `host_arch: aarch64` vs profile `x86_64` |
| Expected reason | `HOST_ARCH_MISMATCH` |
| Zero-candidate | **Not** the scenario objective |

Freeze audit: `run5_arch_profile_present` → eligible; `run5_arch_profile_host_arch_mismatch` → `HOST_ARCH_MISMATCH`.

## Run J — second candidate plan

| Item | Value |
|------|-------|
| Candidate 1 | Canonical T2 `a5576257…` rev 3 (existing) |
| Candidate 2 source | **Run 6** `E_prefix_drift_windows` |
| Mechanism | Material `windows_version` change in disposable clone → new verified Bridge run → new `bridge_manifest_hash` / revision |
| Shared identity | Same `program_identity_key`, same host class, same bridge family |
| Material difference | `windows_version` drift dimension |
| Why revision not attach | Manifest hash change is intentional drift evidence |
| Ranking difference | `drift_penalty` + manifest hash divergence |
| Legacy profiles | Excluded (`WINEPREFIX_MANIFEST_IDENTITY_LEAK`) |
| Precondition | Run 13 blocked until query passes |

### Run J precondition query

```sql
WITH eligible AS (
  SELECT p.profile_id, p.bridge_manifest_hash, p.profile_revision
  FROM compatibility_profiles p
  JOIN compatibility_profile_program_fingerprints pf ON pf.profile_id = p.profile_id
  WHERE pf.executable_hash = '108168df2b9679c5ef4004a5fa63990c99b189661ee3cac4bb8f9dd467ad6d69'
    AND p.trust_state = 'locally_verified'
    AND p.lifecycle_state IN ('ACTIVE', 'VERIFIED')
    AND p.profile_id NOT IN (
      '425f8664-7ddd-4a99-b984-435051027e8f',
      'bebf5c5f-6719-4ac2-8e75-29ac6c839bf3',
      '6aec0dd2-e298-4173-aec3-603e2aae691b',
      '9b0cf7ff-aca8-44ee-b354-28505ac3c60d'
    )
)
SELECT COUNT(*) AS eligible_count,
       COUNT(DISTINCT bridge_manifest_hash) AS distinct_manifests
FROM eligible;
```

Require `eligible_count >= 2` AND `distinct_manifests >= 2` before run-13.

## Source snapshots

See `data/validation/campaigns/pilot-003-source-snapshots.json`.

Campaign guard: `ALMA_BRIDGE_VALIDATION_CAMPAIGN_SOURCE_SNAPSHOT=$PILOT003_ROOT/snapshots`

## Run F invariant

`tests/test_profile_shadow.py::test_run_f_profile_reconstruction_blocked_when_reuse_disabled`
