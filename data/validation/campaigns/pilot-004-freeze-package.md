# Pilot-004 Corrective Package (DRAFT — NOT APPROVED FOR EXECUTION)

**Campaign:** `shadow-validation-pilot-004`  
**Predecessor:** `shadow-validation-pilot-003` (`aborted_non_promotable`)  
**Status:** Freeze complete; `ready_for_execution_approval`. Execution NOT approved.

## Pilot-003 Closure Summary

Pilot-003 is classified **ABORTED_NON_PROMOTABLE**. See `shadow-validation-pilot-003-closure.json`.

- Completed/registered runs: 1–11
- Not started: 12–13
- Final DB hash preserved: `d8561a48f09df41ed722b1d396d8f8de5ebd7f53f94cf43818e138fbca2ee4d3`
- Imported trust fixture mutation preserved in aborted DB (do not restore)
- Pilot-001/002/003 evidence excluded from promotion gates

## Root-Cause Analysis (Five Defects)

| Defect | Root cause | Pilot-004 fix |
|--------|------------|---------------|
| INVALID_LABEL_TYPE | Executor used `shadow_observation_only` (trust category) as operator label | Typed `ValidationLabelType` / `TrustCategory`; semantic validator rejects; Run 11 uses `rejected_correct` |
| POST_HOC_HOST_OVERLAY | Runs 4–5 evaluated overlay after prediction | `host_payload_overlay` fed to `ProfileShadowService.create_prediction()` before planner; `pre_plan_overlay: true` required at freeze |
| WINDOWS_VERSION_DRIFT_NOT_INDUCED | Shadow prediction ran after `require_wine_windows_version` repair | Shadow prediction moved before wine version repair; deterministic win7 mutation sequence |
| COMPONENT_DRIFT_NOT_INDUCED | Executor added corefonts instead of removing frozen component | T2 snapshot includes `corefonts`; Run 7 removes marker files; drift inspector detects `COMPONENT_MISSING` |
| KNOWN_FAILURE_SCENARIO_DID_NOT_FAIL | WordPad succeeded on host | Run 9 removes target executable from disposable clone before launch |
| RUN_J_CANDIDATE_PROVENANCE_MISMATCH | Second candidate predated campaign (`audit-wine-gui`) | SETUP-T2-B documented setup run creates second eligible manifest before freeze |

## Duplicate Profile Metric

**Pilot-003 symptom:** `no_duplicate_profile_defects = 0.55` (11/20 comparisons).

**Root cause:** `build_shadow_comparison_metrics` flagged `duplicate_predicted_lineage=1` whenever both `profile_candidate_id` and `predicted_profile_id` existed — normal for shadow mode with independent planner.

**Fix:** Duplicate only when `promoted_profile_id != predicted_profile_id` (redundant new profile creation).

## Corrective Engineering Deliverables

- `profile_shadow_validation_labels.py` — typed label/trust separation
- `campaign_semantic_validator.py` — semantic freeze validation + resolved plan
- `prefix_drift.py` — deterministic drift helpers
- Pre-plan host overlay in `ShadowPlanningInputs` / orchestrator
- Shadow prediction before wine version repair
- Component drift inspection (`COMPONENT_MISSING`)
- Duplicate metric correction

## Run J Candidate Plan (Pre-Freeze Setup Required)

| Candidate | Source | Role |
|-----------|--------|------|
| `a5576257…` (canonical T2) | SETUP-T2-A | Candidate 1 — stable verified profile |
| TBD at freeze | SETUP-T2-B | Candidate 2 — alternate verified manifest via normal Bridge (e.g. material env difference without path identity) |

SETUP-T2-B must complete before freeze. Run 6 windows drift does **not** assume second candidate creation.

## Feature Flags (unchanged)

```
ALMA_BRIDGE_COMPATIBILITY_PROFILES_ENABLED=true
ALMA_BRIDGE_COMPATIBILITY_PROFILE_CREATION_ENABLED=true
ALMA_BRIDGE_COMPATIBILITY_PROFILE_SHADOW_MODE=true
ALMA_BRIDGE_COMPATIBILITY_PROFILE_REUSE_ENABLED=false
ALMA_BRIDGE_OPERATOR_ENABLED=false
ALMA_BRIDGE_OPERATOR_ALLOW_MUTATIONS=false
ALMA_BRIDGE_VALIDATION_CAMPAIGN_MODE=true
```

## Next Steps (Operator)

1. Run SETUP-T2-B to create second eligible candidate
2. Capture source snapshots for Pilot-004
3. Run `alma-bridge-shadow-validation validate-freeze` — must pass with zero errors
4. Backup `outcomes.db` at freeze
5. Request execution approval explicitly

**Do not execute Pilot-004 until approved.**
