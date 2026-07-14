# Pilot-004 Final Freeze Approval Package

**Date:** 2026-07-14  
**Status:** `ready_for_execution_approval` — **scenario execution NOT APPROVED**  
**Corrective commit:** `68ef1381cff491edd1b743f2b1624845d79bb7f7`  
**Freeze commit:** _(recorded at commit time)_

---

## 1. Pilot-003 closure (unchanged)

| Field | Value |
|-------|-------|
| Status | `aborted_non_promotable` |
| Abort reason | `INVALID_LABEL_TYPE` |
| Completed runs | 1–11 |
| Not started | 12–13 |
| Final DB hash (closure) | `d8561a48f09df41ed722b1d396d8f8de5ebd7f53f94cf43818e138fbca2ee4d3` |
| Do not resume | true |

Record: `data/validation/campaigns/shadow-validation-pilot-003-closure.json`

---

## 2. Run J candidates (SETUP-T2-A / SETUP-T2-B)

| Field | Candidate 1 | Candidate 2 |
|-------|-------------|-------------|
| `profile_id` | `a5576257-65b5-485f-a966-8273bccd8146` | `b2a24a3b-c93c-47f1-826e-cd8d967528cd` |
| `profile_revision` | 3 | 4 |
| `profile_lineage_key` | `585c2bdf136dbb74e0e7438b9a3dff0d7d44c420c042f61c5c391ebe40f59a5e` | same |
| `program_identity_key` | `671ffcc52c6e9bcdff0c652a188593b4743d90ad798b54015b95b3487672d09d` | same |
| `executable_hash` | `108168df2b9679c5ef4004a5fa63990c99b189661ee3cac4bb8f9dd467ad6d69` | same |
| `host_compatibility_class_id` | `9f439bf536c9f9ff803e144869cb9be62ef86b298dfa338ef0f0e5530ff5f19d` | same |
| `bridge_family_key` | `77ae04f2f7eb12a50564ee0b3f90417d1c7c828714f303950e66f4fbcf86d842` | same |
| `bridge_manifest_hash` | `0ae990e9b3bbe238c68bf42b940267c01f3b205f0e98a1a701006588fb95e37d` | `22f6da1afcabe13ca4009b004bae454378a1d47f901c35e9863958662d1f2089` |
| `verification_binding_key` | `2a6c58d46c868fc0124704a5664838f04c125b42d036f5c2a6a4d2297c907f59` | same |
| `trust_state` | `locally_verified` | `locally_verified` |
| `source_session_id` | `946b3255-ea00-4948-a9d5-5ef8dffb7517` | `ac43d474-1186-4f56-906b-97e4aca0bd7b` |

**Exact manifest delta (only differing canonical field):**

```json
"environment": {
  "candidate1": {},
  "candidate2": { "WINEDLLOVERRIDES": "winemenubuilder.exe=d" }
}
```

**Justification:** Stable Wine DLL load-order override (`winemenubuilder.exe=d`) is a material, reusable compatibility configuration — not WINEPREFIX, path alias, timestamp, hostname, or ephemeral session state.

**Ranking audit:** both eligible; distinct manifests; predicted winner `b2a24a3b…` rev 4 via `profile_shadow_rank_v1` / `1.0.0`.

---

## 3. Pre-freeze validator

```
alma-bridge-shadow-validation validate-freeze
→ passed: true, issues: []
```

Evidence: `data/validation/evidence/pilot-004/validate-freeze.json`

---

## 4. Dry-run proofs (freeze prep only)

| Proof | Result | Evidence |
|-------|--------|----------|
| Windows drift (Run 6) | win10→win7; `WINDOWS_VERSION_DRIFT` in immutable candidate | `dry-run-windows-drift.json` |
| Component drift (Run 7) | corefonts removed; `COMPONENT_MISSING` in drift engine | `dry-run-component-drift.json` |
| Known failure precondition (Run 9) | target absent; snapshot intact | `dry-run-known-failure-precondition.json` |
| Host overlay (Runs 4–5) | pre-plan overlay; `HOST_ARCH_MISMATCH`; `selected_profile_id=null` | `host-overlay-audit.json` |
| Duplicate metric fix | A=0, B=1, D=0; legacy excluded | `duplicate-metric-audit.json` |

---

## 5. Source snapshots (immutable)

| Key | Path | Aggregate SHA-256 |
|-----|------|-------------------|
| `t2_notepad64` | `~/.local/share/alma-bridge/prefixes/validation/pilot-004/snapshots/source-t2-notepad64-20260714T171541Z` | `0cbbe4a348ae907f0f1cce8c9c1d1d73079c725e79569a6355e323e3a7ff6c8e` |
| `t2_notepad64_corefonts` | `.../source-t2-notepad64-corefonts-20260714T171541Z` | `6ee0586d01eab9f45fa8716362552b80588239142b521955b56b463e87491d95` |
| `t3_wordpad64` | `.../source-t3-wordpad64-20260714T171541Z` | `2e482c17aaacdf5d2f55153174c0494d2ae8904ff339f0c63a2a5c5eda4a8607` |
| `t3_notepad32` | `.../source-t3-notepad32-20260714T171541Z` | `874d2d41c96867efc302222fe2212048ccb83e498bdd0db72555d4cc79e6eed2` |

Registry: `data/validation/campaigns/pilot-004-source-snapshots.json`

---

## 6. Tests (authoritative)

| Suite | Result |
|-------|--------|
| Focused (pilot004/shadow/validator/binding/guard) | **62 passed** |
| Full `PYTHONPATH=. pytest -q` | **586 passed, 0 failed** |

---

## 7. Campaign input hashes (pre-commit tree)

| Artifact | SHA-256 |
|----------|---------|
| `shadow-validation-pilot-004.json` | `7349e3a2c773b1ddce51215a65eada6a6f306fd2d6ba24d70cd4d7e3016bcbf9` |
| `pilot-004-matrix.json` | `4d064f28db51006b58a07fab57723eb375d45facf55b865fc7fb178be3910224` |
| `pilot-004-commands.md` | `5ae2a5129214fccc66ce15a3d402fe388346e728908489f71129958964712379` |
| `shadow_scenario_manifest_v1.json` | `8a0f95a46ccadd57665f0a24e6b6eeb4fd8d6c6a17a3d97aa9ce6a10f4dabf28` |
| Live `outcomes.db` | `4dbfc27e63f8134bc0f9033b09b88dcfcee7f0ee3468a6fa4ca93351b1f223cf` |

---

## 8. Policy confirmations

- Pilot-001/002/003 evidence **excluded** from promotion gates
- Ascension remains **research-only** / guard reference only
- Active reuse: **false**
- Campaign status: `ready_for_execution_approval` (not `in_progress`)
- **Do not execute Pilot-004 until explicit approval**

---

## 9. Required feature flags

```
ALMA_BRIDGE_COMPATIBILITY_PROFILES_ENABLED=true
ALMA_BRIDGE_COMPATIBILITY_PROFILE_CREATION_ENABLED=true
ALMA_BRIDGE_COMPATIBILITY_PROFILE_SHADOW_MODE=true
ALMA_BRIDGE_COMPATIBILITY_PROFILE_REUSE_ENABLED=false
ALMA_BRIDGE_OPERATOR_ENABLED=false
ALMA_BRIDGE_OPERATOR_ALLOW_MUTATIONS=false
ALMA_BRIDGE_VALIDATION_CAMPAIGN_MODE=true
```
