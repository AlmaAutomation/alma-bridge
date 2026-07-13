# Pilot-001 Execution Commands

Source `scripts/validation/pilot_env.sh` before every run. Mutating scenarios must pass `prefix_guard.sh`.

```bash
source /home/joshua/Desktop/Alma/alma-bridge/scripts/validation/pilot_env.sh
cd "$REPO"
```

---

## Run 1 — A_stable_repeat_success

**Prerequisites:** Profile may be seeded by this run; primary prefix read-only.

```bash
source "$REPO/scripts/validation/pilot_env.sh"
cd "$REPO"
export WINEPREFIX="$PRIMARY_PREFIX"

curl -s -X POST $API/bridge/run -H 'Content-Type: application/json' -d "$(jq -n \
  --arg fp "$ASCENSION_LAUNCHER" --arg wp "$WINEPREFIX" \
  '{file_path:$fp, wine_prefix:$wp, max_attempts:12}')" \
  | tee data/validation/evidence/pilot-001/run01/response.json

SESSION_ID=$(jq -r .session_id data/validation/evidence/pilot-001/run01/response.json)
SHADOW_EVENT_ID=$(sqlite3 data/outcomes.db \
  "SELECT shadow_event_id FROM compatibility_profile_shadow_predictions WHERE session_id='$SESSION_ID';")

alma-bridge-shadow-validation register-run --session-id "$SESSION_ID" \
  --scenario-id A_stable_repeat_success --program-kind pe_electron_launcher \
  --application-family ascension

alma-bridge-shadow-validation export --session-id "$SESSION_ID" \
  --output data/validation/evidence/pilot-001/run01/export.json
```

---

## Run 2 — B_relocated_executable

```bash
mkdir -p /tmp/validation/pilot-001
cp -a "$ASCENSION_LAUNCHER" /tmp/validation/pilot-001/launcher-copy.exe
export COPY=/tmp/validation/pilot-001/launcher-copy.exe
export WINEPREFIX="<same_prefix_as_run1>"

curl -s -X POST $API/bridge/run -H 'Content-Type: application/json' -d "$(jq -n \
  --arg fp "$COPY" --arg wp "$WINEPREFIX" \
  '{file_path:$fp, wine_prefix:$wp, max_attempts:12}')" \
  | tee data/validation/evidence/pilot-001/run02/response.json

SESSION_ID=$(jq -r .session_id data/validation/evidence/pilot-001/run02/response.json)
alma-bridge-shadow-validation register-run --session-id "$SESSION_ID" \
  --scenario-id B_relocated_executable --program-kind pe_electron_launcher \
  --application-family ascension
alma-bridge-shadow-validation export --session-id "$SESSION_ID" \
  --output data/validation/evidence/pilot-001/run02/export.json
rm -f /tmp/validation/pilot-001/launcher-copy.exe
```

---

## Run 3 — D_incompatible_host_drift (wine major)

**Setup:** Use a profile created under a different documented Wine major (second bottle/machine) OR label against known mismatch. Do not upgrade system Wine.

```bash
export WINEPREFIX="$HOME/.local/share/alma-bridge/prefixes/validation/pilot-001/run-03"
# Run bridge against mismatched profile context (document wine --version before/after)

curl -s -X POST $API/bridge/run -H 'Content-Type: application/json' -d "$(jq -n \
  --arg fp "$ASCENSION_LAUNCHER" --arg wp "$WINEPREFIX" \
  '{file_path:$fp, wine_prefix:$wp, max_attempts:12}')" \
  | tee data/validation/evidence/pilot-001/run03/response.json

SESSION_ID=$(jq -r .session_id data/validation/evidence/pilot-001/run03/response.json)
alma-bridge-shadow-validation register-run --session-id "$SESSION_ID" \
  --scenario-id D_incompatible_host_drift --program-kind pe_electron_launcher \
  --application-family ascension

alma-bridge-shadow-validation add-label --shadow-event-id "$(sqlite3 data/outcomes.db \
  "SELECT shadow_event_id FROM compatibility_profile_shadow_predictions WHERE session_id='$SESSION_ID';")" \
  --label-type rejected_correct --reviewer "$OPERATOR" \
  --reason "Wine major mismatch vs profile host class"
```

---

## Run 4 — D_incompatible_host_drift (capability)

```bash
export PILOT_PREFIX="$HOME/.local/share/alma-bridge/prefixes/validation/pilot-001/run-04"
cp -a "$SOURCE_PREFIX" "$PILOT_PREFIX"
export WINEPREFIX="$PILOT_PREFIX"

curl -s -X POST $API/bridge/run -H 'Content-Type: application/json' -d "$(jq -n \
  --arg fp "$INSTALLER_EXE" --arg wp "$WINEPREFIX" \
  '{file_path:$fp, wine_prefix:$wp, max_attempts:12}')" \
  | tee data/validation/evidence/pilot-001/run04/response.json

SESSION_ID=$(jq -r .session_id data/validation/evidence/pilot-001/run04/response.json)
alma-bridge-shadow-validation register-run --session-id "$SESSION_ID" \
  --scenario-id D_incompatible_host_drift --program-kind pe_installer \
  --application-family installer
rm -rf "$PILOT_PREFIX"
```

---

## Run 5 — E_prefix_drift_windows

```bash
export PILOT_PREFIX="$HOME/.local/share/alma-bridge/prefixes/validation/pilot-001/run-05"
cp -a "$SOURCE_PREFIX" "$PILOT_PREFIX"
# Record: read_wine_windows_version "$PILOT_PREFIX" (before)
# Mutate Windows version in clone only (winecfg/registry)
export WINEPREFIX="$PILOT_PREFIX"

curl -s -X POST $API/bridge/run -H 'Content-Type: application/json' -d "$(jq -n \
  --arg fp "$ASCENSION_LAUNCHER" --arg wp "$WINEPREFIX" \
  '{file_path:$fp, wine_prefix:$wp, max_attempts:12}')" \
  | tee data/validation/evidence/pilot-001/run05/response.json

SESSION_ID=$(jq -r .session_id data/validation/evidence/pilot-001/run05/response.json)
alma-bridge-shadow-validation register-run --session-id "$SESSION_ID" \
  --scenario-id E_prefix_drift_windows --program-kind pe_electron_launcher \
  --application-family ascension
rm -rf "$PILOT_PREFIX"
```

---

## Run 6 — E_prefix_drift_config

```bash
export PILOT_PREFIX="$HOME/.local/share/alma-bridge/prefixes/validation/pilot-001/run-06"
cp -a "$SOURCE_PREFIX" "$PILOT_PREFIX"
# Snapshot config hashes before; modify one config file in clone
sha256sum "$PILOT_PREFIX"/user.reg "$PILOT_PREFIX"/system.reg > data/validation/evidence/pilot-001/run06/prefix-checksums-before.txt
export WINEPREFIX="$PILOT_PREFIX"

curl -s -X POST $API/bridge/run -H 'Content-Type: application/json' -d "$(jq -n \
  --arg fp "$ASCENSION_LAUNCHER" --arg wp "$WINEPREFIX" \
  '{file_path:$fp, wine_prefix:$wp, max_attempts:12}')" \
  | tee data/validation/evidence/pilot-001/run06/response.json

SESSION_ID=$(jq -r .session_id data/validation/evidence/pilot-001/run06/response.json)
alma-bridge-shadow-validation register-run --session-id "$SESSION_ID" \
  --scenario-id E_prefix_drift_component --program-kind pe_electron_launcher \
  --application-family ascension
rm -rf "$PILOT_PREFIX"
```

---

## Run 7 — G_known_compatibility_failure

```bash
export PILOT_PREFIX="$HOME/.local/share/alma-bridge/prefixes/validation/pilot-001/run-07"
cp -a "$SOURCE_PREFIX" "$PILOT_PREFIX"
# Remove dotnet/vcrun from clone only
export WINEPREFIX="$PILOT_PREFIX"

curl -s -X POST $API/bridge/run -H 'Content-Type: application/json' -d "$(jq -n \
  --arg fp "$ASCENSION_LAUNCHER" --arg wp "$WINEPREFIX" \
  '{file_path:$fp, wine_prefix:$wp, max_attempts:12}')" \
  | tee data/validation/evidence/pilot-001/run07/response.json

SESSION_ID=$(jq -r .session_id data/validation/evidence/pilot-001/run07/response.json)
alma-bridge-shadow-validation register-run --session-id "$SESSION_ID" \
  --scenario-id G_known_compatibility_failure --program-kind pe_electron_launcher \
  --application-family ascension

alma-bridge-shadow-validation add-label --shadow-event-id "$(sqlite3 data/outcomes.db \
  "SELECT shadow_event_id FROM compatibility_profile_shadow_predictions WHERE session_id='$SESSION_ID';")" \
  --label-type eligible_correct --reviewer "$OPERATOR" \
  --reason "Eligible profile; execution failed due to missing runtime in prefix"
rm -rf "$PILOT_PREFIX"
```

---

## Run 8 — H_unrelated_runtime_failure

```bash
curl -s -X POST $API/bridge/run -H 'Content-Type: application/json' -d "$(jq -n \
  --arg fp "$NATIVE_SCRIPT" \
  '{file_path:$fp, max_attempts:1}')" \
  | tee data/validation/evidence/pilot-001/run08/response.json

SESSION_ID=$(jq -r .session_id data/validation/evidence/pilot-001/run08/response.json)
alma-bridge-shadow-validation register-run --session-id "$SESSION_ID" \
  --scenario-id H_unrelated_runtime_failure --program-kind native_script \
  --application-family generic

alma-bridge-shadow-validation add-label --shadow-event-id "$(sqlite3 data/outcomes.db \
  "SELECT shadow_event_id FROM compatibility_profile_shadow_predictions WHERE session_id='$SESSION_ID';")" \
  --label-type indeterminate --reviewer "$OPERATOR" \
  --reason "Timeout/unrelated failure; insufficient evidence for eligibility judgment"
```

---

## Run 9 — I_trust_state_imported

Label post-run: `rejected_correct` if imported profile is blocked from winner selection; `winner_correct` only if another locally verified profile is correctly selected.

```bash
source "$REPO/scripts/validation/pilot_env.sh"
# TEST profile only:
# python3 -c "import sqlite3; c=sqlite3.connect('data/outcomes.db'); c.execute(\"UPDATE compatibility_profiles SET trust_state='imported' WHERE profile_id=?\", ('<TEST_PROFILE_ID>',)); c.commit()"

export WINEPREFIX="$PRIMARY_PREFIX"
curl -s -X POST $API/bridge/run -H 'Content-Type: application/json' -d "$(jq -n \
  --arg fp "$ASCENSION_LAUNCHER" --arg wp "$WINEPREFIX" \
  '{file_path:$fp, wine_prefix:$wp, max_attempts:12}')" \
  | tee data/validation/evidence/pilot-001/run09/response.json

SESSION_ID=$(jq -r .session_id data/validation/evidence/pilot-001/run09/response.json)
alma-bridge-shadow-validation register-run --session-id "$SESSION_ID" \
  --scenario-id I_trust_state_imported --program-kind pe_electron_launcher \
  --application-family ascension

# Restore: UPDATE trust_state='locally_verified'
```

---

## Run 10 — J_multiple_candidate_ranking

**Prerequisites:** Run `shadow-validation-pilot-001-run10-precheck.md` query first. Block if `CANDIDATE_SET_OK` is absent.

```bash
source "$REPO/scripts/validation/pilot_env.sh"
export WINEPREFIX="$PRIMARY_PREFIX"
curl -s -X POST $API/bridge/run -H 'Content-Type: application/json' -d "$(jq -n \
  --arg fp "$ASCENSION_LAUNCHER" --arg wp "$WINEPREFIX" \
  '{file_path:$fp, wine_prefix:$wp, max_attempts:12}')" \
  | tee data/validation/evidence/pilot-001/run10/response.json

SESSION_ID=$(jq -r .session_id data/validation/evidence/pilot-001/run10/response.json)
SHADOW_EVENT_ID=$(sqlite3 data/outcomes.db \
  "SELECT shadow_event_id FROM compatibility_profile_shadow_predictions WHERE session_id='$SESSION_ID';")

alma-bridge-shadow-validation register-run --session-id "$SESSION_ID" \
  --scenario-id J_multiple_candidate_ranking --program-kind pe_electron_launcher \
  --application-family ascension

sqlite3 data/outcomes.db \
  "SELECT profile_id, profile_revision, eligibility_status, final_rank_score FROM compatibility_profile_shadow_candidates WHERE shadow_event_id='$SHADOW_EVENT_ID';"
```

---

## Run 11 — F_clean_prefix_reconstruction

Fresh disposable prefix via `wineboot -i`. Label from shadow eligibility evidence, not application success.

```bash
source "$REPO/scripts/validation/pilot_env.sh"
export PILOT_PREFIX="$VALIDATION_ROOT/run-11"
rm -rf "$PILOT_PREFIX"
mkdir -p "$PILOT_PREFIX"
export WINEPREFIX="$PILOT_PREFIX"
WINEPREFIX="$PILOT_PREFIX" wineboot -i

curl -s -X POST $API/bridge/run -H 'Content-Type: application/json' -d "$(jq -n \
  --arg fp "$ASCENSION_LAUNCHER" --arg wp "$WINEPREFIX" \
  '{file_path:$fp, wine_prefix:$wp, max_attempts:12}')" \
  | tee data/validation/evidence/pilot-001/run11/response.json

SESSION_ID=$(jq -r .session_id data/validation/evidence/pilot-001/run11/response.json)
alma-bridge-shadow-validation register-run --session-id "$SESSION_ID" \
  --scenario-id F_clean_prefix_reconstruction --program-kind pe_electron_launcher \
  --application-family ascension
alma-bridge-shadow-validation export --session-id "$SESSION_ID" \
  --output data/validation/evidence/pilot-001/run11/export.json
rm -rf "$PILOT_PREFIX"
```

---

## Run 12 — I_trust_state_invalidated

Scoped invalidation on test profile only. Expect `INVALIDATED_PROFILE_DIAGNOSTIC_ONLY`.

```bash
source "$REPO/scripts/validation/pilot_env.sh"
# Insert scoped invalidation on TEST profile, then:
export WINEPREFIX="$PRIMARY_PREFIX"
curl -s -X POST $API/bridge/run -H 'Content-Type: application/json' -d "$(jq -n \
  --arg fp "$ASCENSION_LAUNCHER" --arg wp "$WINEPREFIX" \
  '{file_path:$fp, wine_prefix:$wp, max_attempts:12}')" \
  | tee data/validation/evidence/pilot-001/run12/response.json

SESSION_ID=$(jq -r .session_id data/validation/evidence/pilot-001/run12/response.json)
SHADOW_EVENT_ID=$(sqlite3 data/outcomes.db \
  "SELECT shadow_event_id FROM compatibility_profile_shadow_predictions WHERE session_id='$SESSION_ID';")
alma-bridge-shadow-validation register-run --session-id "$SESSION_ID" \
  --scenario-id I_trust_state_invalidated --program-kind pe_electron_launcher \
  --application-family ascension
alma-bridge-shadow-validation add-label --shadow-event-id "$SHADOW_EVENT_ID" \
  --label-type rejected_correct --reviewer "$REVIEWER" \
  --reason "Invalidated profile observable diagnostically; not selected as winner"
# Deactivate invalidation / restore profile state after evidence export
```

---

## End-of-pilot

```bash
alma-bridge-shadow-validation analyze-failures
alma-bridge-shadow-validation gates | tee data/validation/evidence/pilot-001/gates.json
alma-bridge-shadow-validation report > data/validation/evidence/pilot-001/report.json
pytest -q --tb=line -ra  # must remain >=505 passed
```

Update `shadow-validation-pilot-001.json`: `status`, `completed_scenario_ids`, `completed_at_utc`.
