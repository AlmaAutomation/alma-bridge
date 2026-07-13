# Shadow Validation Runbook (A–J Matrix)

**Purpose:** Collect real shadow evidence to evaluate promotion gates before any active-reuse decision.  
**Scope:** Operational only — no code, threshold, ranking, or planner changes.

---

## 1. Environment Preparation

### Feature flags (`.env` or shell)

```bash
export ALMA_BRIDGE_COMPATIBILITY_PROFILES_ENABLED=true
export ALMA_BRIDGE_COMPATIBILITY_PROFILE_CREATION_ENABLED=true   # seed profiles from verified runs
export ALMA_BRIDGE_COMPATIBILITY_PROFILE_SHADOW_MODE=true
export ALMA_BRIDGE_COMPATIBILITY_PROFILE_REUSE_ENABLED=false     # must stay false
```

Confirm before each session:

```bash
grep COMPATIBILITY_PROFILE .env
```

### Backup `outcomes.db`

```bash
cd /home/joshua/Desktop/Alma/alma-bridge
cp data/outcomes.db "data/outcomes.db.bak.$(date -u +%Y%m%dT%H%M%SZ)"
```

Optional isolated validation DB (recommended for destructive scenarios):

```bash
cp data/outcomes.db data/outcomes.validation.db
export ALMA_BRIDGE_DB_PATH=data/outcomes.validation.db
```

### Isolated test prefixes

```bash
export VALIDATION_PREFIX_ROOT="$HOME/.local/share/alma-bridge/prefixes/validation"
mkdir -p "$VALIDATION_PREFIX_ROOT"

# Per-scenario disposable prefix (example)
export WINEPREFIX="$VALIDATION_PREFIX_ROOT/E_windows_drift_001"
wineboot -i   # only on fresh prefixes
```

**Never use the primary Ascension production prefix for E/G destructive drift.**  
Production prefixes live under `~/.local/share/alma-bridge/prefixes/` — treat non-`validation/` subdirs as protected.

### Logs

| Source | Location |
|---|---|
| Bridge API server | Terminal stdout/stderr where `alma-bridge` / uvicorn runs |
| Session progress | `bridge_sessions.summary`, `bridge_session_transitions` in SQLite |
| Shadow events | `compatibility_profile_shadow_events` table |
| Structured profile logs | Python logger `alma_bridge.compatibility.profiles` (stdout) |

Capture per run:

```bash
script -q -f "data/validation/evidence/$(date -u +%Y%m%d)/run_${SESSION_ID}.log"
# ... run scenario ...
exit
```

### Artifact / output directory

```bash
mkdir -p data/validation/evidence/$(date -u +%Y%m%d)/{exports,snapshots,labels}
export VALIDATION_EVIDENCE_DIR="data/validation/evidence/$(date -u +%Y%m%d)"
```

### Reset validation overlay only (keep production outcomes + profiles)

Clears registration, labels, and failure analyses — **does not** delete shadow predictions, comparisons, profiles, or bridge sessions:

```bash
sqlite3 data/outcomes.db <<'SQL'
DELETE FROM compatibility_profile_shadow_failure_analysis;
DELETE FROM compatibility_profile_shadow_labels;
DELETE FROM compatibility_profile_shadow_validation_runs;
SQL
alma-bridge-shadow-validation sync-manifest
```

To re-sync scenario definitions without deleting shadow evidence:

```bash
alma-bridge-shadow-validation sync-manifest
```

---

## 2. Scenario Execution Table

**Target programs (rotate across runs — do not repeat the same executable + prefix + scenario):**

| Slot | Program kind | Suggested target |
|---|---|---|
| P1 | `pe_electron_launcher` | Ascension installed launcher (Wine) |
| P2 | `pe_installer` | Windows installer `.exe` (disposable prefix) |
| P3 | `native_script` | Local `.sh` test binary |

**Bridge run (API):**

```bash
curl -s -X POST http://127.0.0.1:9010/bridge/run \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "/path/to/target",
    "wine_prefix": "'"$WINEPREFIX"'",
    "max_attempts": 12
  }' | tee "$VALIDATION_EVIDENCE_DIR/run_response.json"
```

Extract `session_id`:

```bash
SESSION_ID=$(jq -r .session_id "$VALIDATION_EVIDENCE_DIR/run_response.json")
echo "$SESSION_ID"
```

**Register run:**

```bash
alma-bridge-shadow-validation register-run \
  --session-id "$SESSION_ID" \
  --scenario-id "<SCENARIO_ID>" \
  --program-kind "<pe_electron_launcher|pe_installer|native_script>" \
  --application-family "<ascension|installer|generic>"
```

**Capture `shadow_event_id`:**

```bash
SHADOW_EVENT_ID=$(sqlite3 data/outcomes.db \
  "SELECT shadow_event_id FROM compatibility_profile_shadow_predictions WHERE session_id='$SESSION_ID';")
echo "$SHADOW_EVENT_ID"
```

---

### A_stable_repeat_success

| Field | Value |
|---|---|
| **Prerequisites** | Profile exists for target hash; shadow flags on; prefix unchanged since profile creation |
| **Setup** | Use same `WINEPREFIX` and binary as profile source run |
| **Target** | P1 Ascension launcher (primary) |
| **Induce condition** | None — repeat verified configuration |
| **Run** | Standard `/bridge/run` with stable path + prefix |
| **Expected shadow** | Eligible; winner = existing profile; no drift; strategy matches profile |
| **Cleanup** | None |

---

### B_relocated_executable

| Field | Value |
|---|---|
| **Prerequisites** | Profile for original path/hash; content unchanged |
| **Setup** | `cp /original/launcher.exe /tmp/validation/launcher-copy.exe` (same bytes) |
| **Target** | Copy of P1 or P2 |
| **Induce condition** | Different path only |
| **Run** | `/bridge/run` with `file_path` = copy path, same `wine_prefix` |
| **Expected shadow** | Eligible (path-free identity); same winner; no new revision |
| **Cleanup** | `rm /tmp/validation/launcher-copy.exe` |

---

### C_compatible_host_drift

| Field | Value |
|---|---|
| **Prerequisites** | Profile on current host class; document host snapshot first |
| **Setup** | Record `host_compatibility_class_id` from prediction; after minor OS patch **or** document equivalent metadata-only drift for labeling |
| **Target** | P1 or P3 |
| **Induce condition** | Patch-level change that does **not** change Wine major or arch (no driver/package experiments) |
| **Run** | `/bridge/run` after host change |
| **Expected shadow** | Eligible; possible host-class dimension note; winner likely unchanged |
| **Cleanup** | Restore documented host state or label with evidence refs |

**Safety:** Do not install kernel, drivers, or Wine upgrades for this scenario.

---

### D_incompatible_host_drift

| Field | Value |
|---|---|
| **Prerequisites** | Profile with `wine_major` in host fingerprint |
| **Setup** | **Simulation preferred:** use SQLite + labeling to mark expected `WINE_MAJOR_INCOMPATIBLE` OR run against profile created under different documented Wine major (second machine/bottle) — **do not upgrade system Wine** |
| **Target** | P1 |
| **Induce condition** | Mismatched wine major vs profile host class |
| **Run** | `/bridge/run` |
| **Expected shadow** | Rejected; codes include `WINE_MAJOR_INCOMPATIBLE`; no winner |
| **Cleanup** | N/A if simulated; else restore Wine environment |

**Variants (separate runs):** arch mismatch profile (if available), missing capability profile.

---

### E_prefix_drift_windows

| Field | Value |
|---|---|
| **Prerequisites** | Profile tied to known `windows_version`; disposable prefix copy |
| **Setup** | `cp -a "$SOURCE_PREFIX" "$VALIDATION_PREFIX_ROOT/E_win_drift"`; record `read_wine_windows_version` output |
| **Target** | P1 on disposable prefix |
| **Induce condition** | `winecfg` or documented registry tweak to change Windows version **in copy only** |
| **Run** | `/bridge/run` with drifted `wine_prefix` |
| **Expected shadow** | Eligible; drift `windows_version`; winner with drift detected |
| **Cleanup** | `rm -rf "$VALIDATION_PREFIX_ROOT/E_win_drift"` |

---

### E_prefix_drift_component

| Field | Value |
|---|---|
| **Prerequisites** | Profile manifest lists winetricks component |
| **Setup** | Prefix copy; record installed component list / checksum snapshot |
| **Target** | P1 or P2 |
| **Induce condition** | Remove component files from **copy only** (not production prefix) |
| **Run** | `/bridge/run` |
| **Expected shadow** | Eligible; drift `installed_components` (may be indeterminate-readonly) |
| **Cleanup** | Delete prefix copy or reinstall component |

---

### F_clean_prefix_reconstruction

| Field | Value |
|---|---|
| **Prerequisites** | Profile exists; fresh empty prefix |
| **Setup** | `WINEPREFIX="$VALIDATION_PREFIX_ROOT/F_clean_001"; wineboot -i` |
| **Target** | P1 |
| **Induce condition** | Empty prefix, no prior install in this prefix |
| **Run** | `/bridge/run` (may fail execution — still valid shadow evidence) |
| **Expected shadow** | Eligible; drift `prefix_unavailable` / indeterminate prefix signals |
| **Cleanup** | `rm -rf "$VALIDATION_PREFIX_ROOT/F_clean_001"` |

---

### G_known_compatibility_failure

| Field | Value |
|---|---|
| **Prerequisites** | Profile exists; disposable prefix |
| **Setup** | Remove .NET/VC++ runtimes from **prefix copy** only; record checksums before |
| **Target** | P1 or P2 requiring runtimes |
| **Induce condition** | Missing dependency → known failure signature |
| **Run** | `/bridge/run` expecting FAILED terminal state |
| **Expected shadow** | Eligible profile; execution fails; comparison still labelable |
| **Cleanup** | Restore runtimes in copy or delete prefix |

---

### H_unrelated_runtime_failure

| Field | Value |
|---|---|
| **Prerequisites** | Profile exists |
| **Setup** | Choose one: cancel mid-run, unmount path, or very low `max_attempts` + slow network dep |
| **Target** | P3 native or P1 |
| **Induce condition** | Timeout / cancel / file access — **not** compatibility mismatch |
| **Run** | `/bridge/run` or cancel via API; expect FAILED/CANCELLED |
| **Expected shadow** | Eligible; comparison often **indeterminate** |
| **Cleanup** | None |

---

### I_trust_state_imported

| Field | Value |
|---|---|
| **Prerequisites** | Test profile row |
| **Setup** | `sqlite3 data/outcomes.db "UPDATE compatibility_profiles SET trust_state='imported' WHERE profile_id='<ID>';"` — **test profile only** |
| **Target** | Matching executable |
| **Run** | `/bridge/run` |
| **Expected shadow** | Eligible + `shadow_observation_only`; **no winner selected** |
| **Cleanup** | `UPDATE ... SET trust_state='locally_verified' ...` |

---

### I_trust_state_invalidated

| Field | Value |
|---|---|
| **Prerequisites** | Test profile |
| **Setup** | Insert scoped invalidation via validation tooling or sqlite on test profile |
| **Run** | `/bridge/run` |
| **Expected shadow** | Rejected `INVALIDATED_PROFILE_DIAGNOSTIC_ONLY`; no winner |
| **Cleanup** | Deactivate invalidation row (`active=0`) |

---

### J_multiple_candidate_ranking

| Field | Value |
|---|---|
| **Prerequisites** | Two profiles: same executable hash, different `bridge_manifest_hash` or `bridge_family_key` |
| **Setup** | Run two verified bridges with different remediation/env (disposable prefixes); confirm two `compatibility_profiles` rows |
| **Target** | P1 |
| **Run** | Third `/bridge/run` — shadow ranks both |
| **Expected shadow** | Both eligible; winner = highest rank score; rank components persisted |
| **Cleanup** | Archive extra test profile rows if needed (document only — do not delete production profiles without approval) |

---

## 3. Safety Controls

1. **Disposable prefixes** under `$VALIDATION_PREFIX_ROOT` for all E/G/F drift.
2. **Never mutate** primary Ascension production prefix for destructive tests.
3. **No host-level** package, kernel, or driver changes during validation.
4. **Copy-before-mutate:** `cp -a` prefix; snapshot wrapper versions, config hashes, DLL overrides before drift.
5. **Record checksums** (`sha256sum`, `read_wine_windows_version`) before and after each drift.
6. **Restore or delete** every validation prefix and trust-state/invalidation override after the run.

---

## 4. Dataset Allocation Plan

Minimum runs to approach gates **without repeating identical (executable + prefix + scenario + host) tuples**:

| Category | Min runs | Notes |
|---|---:|---|
| A_stable_repeat_success | 5 | 2× P1, 1× P2, 1× P3, 1× different Ascension build |
| B_relocated_executable | 4 | Distinct copy paths |
| C_compatible_host_drift | 4 | Document host metadata; label carefully |
| D_incompatible_host_drift | 6 | 2× wine major, 2× arch, 2× capability |
| E_prefix_drift | 12 | 6× windows, 6× component (counts toward **10 drift**) |
| F_clean_prefix_reconstruction | 4 | Fresh prefixes |
| G_known_compatibility_failure | 6 | Distinct failure signatures |
| H_unrelated_runtime_failure | 6 | Expect many indeterminate |
| I_trust_state | 6 | 3× imported, 3× invalidated (**10 rejection** combined with D) |
| J_multiple_candidate_ranking | 8 | ≥2 candidates per run |
| **Total** | **~61** | Yields **50+** labelable if H indeterminate ≤11 |

**Program kind coverage (≥3):** P1 `pe_electron_launcher`, P2 `pe_installer`, P3 `native_script`.

**Diversity rule:** At least one run per scenario_id; no more than **2** runs with identical `(executable_hash, wine_prefix, scenario_id)` unless inducing a **documented different drift variant**.

---

## 5. Evidence Collection (per run)

Save to `$VALIDATION_EVIDENCE_DIR/<scenario_id>_<session_id>/`:

| Artifact | How |
|---|---|
| `scenario_id` | From register-run |
| `session_id` | API response |
| `shadow_event_id` | SQLite query above |
| Candidate profiles | `SELECT * FROM compatibility_profile_shadow_candidates WHERE shadow_event_id=...` |
| Expected result | Manifest + this runbook |
| Terminal state | `bridge_sessions` / API result `success` |
| Verification | `bridge_attempts.verification_json` for winning attempt |
| Logs | `script` capture + API response JSON |
| Env snapshot | `sha256sum`, `WINEPREFIX`, windows version, wine --version, `read_wine_windows_version` |
| Operator label | `add-label` if comparison indeterminate or disputed |

**Export bundle:**

```bash
alma-bridge-shadow-validation export \
  --session-id "$SESSION_ID" \
  --output "$VALIDATION_EVIDENCE_DIR/exports/${SESSION_ID}.json"
```

---

## 6. Labeling Rubric

Label **compatibility correctness**, not application success alone.

| Label | Apply when |
|---|---|
| **eligible_correct** | Profile should be eligible for observation; shadow marked eligible; evidence supports same program/host/binding class |
| **eligible_incorrect** | Profile should be rejected; shadow marked eligible (false eligibility) |
| **rejected_correct** | Rejection correct; reason codes match induced condition (e.g. `WINE_MAJOR_INCOMPATIBLE`) |
| **rejected_incorrect** | Profile should be eligible; shadow rejected (false rejection) |
| **drift_correct** | Drift dimensions match induced prefix/config change (or correctly indeterminate when read-only limits apply) |
| **drift_incorrect** | Drift missed real change or flagged spurious drift |
| **winner_correct** | Selected profile is the best eligible match for the scenario |
| **winner_incorrect** | A different eligible profile should have won, or no winner should have been selected |
| **indeterminate** | Unrelated failure (H), missing evidence, or readonly drift limits prevent fair judgment |

**Do not label** based only on `success: true/false`. A run can fail execution while shadow eligibility is still correct.

```bash
alma-bridge-shadow-validation add-label \
  --shadow-event-id "$SHADOW_EVENT_ID" \
  --label-type eligible_correct \
  --reviewer "<your-id>" \
  --reason "Profile matches hash and host class; failure was missing dotnet in prefix" \
  --profile-id "<profile-uuid>" \
  --evidence "attempt:3,verification_json,session:$SESSION_ID"
```

---

## 7. Daily Workflow

```bash
# Morning: sync manifest, backup DB, check flags
alma-bridge-shadow-validation sync-manifest
cp data/outcomes.db "data/outcomes.db.bak.$(date -u +%Y%m%d)"

# Execute scenarios (see §2); after each run:
alma-bridge-shadow-validation register-run --session-id ... --scenario-id ... --program-kind ...

# Label disputed or indeterminate cases
alma-bridge-shadow-validation add-label --shadow-event-id ... --label-type ... --reviewer ... --reason "..."

# End of day
alma-bridge-shadow-validation analyze-failures
alma-bridge-shadow-validation gates | tee "$VALIDATION_EVIDENCE_DIR/gates_$(date -u +%Y%m%d).json"
alma-bridge-shadow-validation report > "$VALIDATION_EVIDENCE_DIR/report_$(date -u +%Y%m%d).json"

# Export unresolved
sqlite3 data/outcomes.db "SELECT shadow_event_id,session_id FROM compatibility_profile_shadow_comparisons WHERE indeterminate=1;"
# export each...

# Review failures
sqlite3 data/outcomes.db "SELECT failure_kind,scenario_category,shadow_event_id FROM compatibility_profile_shadow_failure_analysis;"
```

**API alternative for gates/report:**

```bash
curl -s http://127.0.0.1:9010/compatibility/shadow/validation/gates | jq .
curl -s http://127.0.0.1:9010/compatibility/shadow/validation/report | jq .
```

---

## 8. Gate Review — Evidence Package Checklist

Before **considering** active reuse (still requires explicit approval):

- [ ] `alma-bridge-shadow-validation gates` → `promotion_ready: true`
- [ ] `report` JSON archived with **≥50** labelable comparisons
- [ ] Per-category metrics: no category with false-eligibility rate > 5% (n≥3)
- [ ] Wilson confidence intervals documented for precision/agreement metrics
- [ ] False eligibility cases: listed, analyzed, root-cause classified
- [ ] False rejection cases: listed, analyzed
- [ ] Drift errors: `drift_incorrect` labels or `incorrect_drift` analyses reviewed
- [ ] Incorrect winners: `winner_incorrect` labels reviewed
- [ ] Unresolved indeterminate: counted; either labeled or excluded with reason
- [ ] Sanitized exports for all disputed sessions
- [ ] Test suite: `pytest -q` → **505+ passed** on release commit
- [ ] Security review: profile artifacts, exports, no secrets/paths in exports
- [ ] `compatibility_profile_reuse_enabled` still **false**
- [ ] Written recommendation from `promotion_gates.recommendation` attached

---

## 9. Quick Reference

| Action | Command |
|---|---|
| Full report | `alma-bridge-shadow-validation report` |
| Gates only | `alma-bridge-shadow-validation gates` |
| Sync manifest | `alma-bridge-shadow-validation sync-manifest` |
| Register | `alma-bridge-shadow-validation register-run --session-id ... --scenario-id ...` |
| Label | `alma-bridge-shadow-validation add-label ...` |
| Analyze | `alma-bridge-shadow-validation analyze-failures` |
| Export | `alma-bridge-shadow-validation export --session-id ... --output ...` |

**Manifest source:** `data/validation/shadow_scenario_manifest_v1.json`
