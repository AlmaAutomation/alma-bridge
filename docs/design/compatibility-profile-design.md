# CompatibilityProfile Design Proposal

**Status:** Design only — not approved for implementation  
**Date:** 2026-07-13  
**Prerequisite:** ADR-001 authoritative lifecycle and verification boundary

## Purpose

`CompatibilityProfile` represents a **previously verified compatibility solution** for a specific
program/host/bridge configuration. It is not a prefix status cache (`PrefixReadinessProfile`),
not a prior-success shortcut, and not a planner or lifecycle owner.

Reuse may accelerate planning and configuration reconstruction, but **every reuse must pass
current `VerificationEngine` evaluation** before a session may reach `SUCCEEDED`.

---

## 1. Domain model

### ProgramFingerprint

Identifies the executable being run.

| Field | Type | Source |
|---|---|---|
| `executable_hash` | SHA-256 | `file_hash()` |
| `normalized_path` | string | resolved path with home/temp normalization |
| `file_size` | int | `stat().st_size` |
| `executable_format` | enum | `pe`, `elf`, `macho`, `script`, `appimage`, `installer` |
| `architecture` | string | PE/ELF arch or host arch for scripts |
| `program_kind` | string | `classify_program_kind()` |
| `product_name` | optional string | PE metadata / AppImage label |
| `product_version` | optional string | PE/file version resource |
| `bundled_file_hashes` | map[str,str] | selective hashes of launcher-adjacent files |

### HostFingerprint

Identifies the execution environment.

| Field | Type | Source |
|---|---|---|
| `os_id` | string | `/etc/os-release` ID |
| `os_version_id` | string | VERSION_ID |
| `kernel_version` | string | `uname -r` |
| `host_arch` | string | `profile_hardware()` |
| `wine_version` | optional string | `wine --version` |
| `proton_version` | optional string | Proton path metadata |
| `gpu_identity` | optional string | normalized PCI/driver id |
| `container_capable` | bool | `sandbox_ready()` |
| `dependency_versions` | map[str,str] | dotnet, vcrun, winetricks core set |

### BridgeFingerprint

Identifies the verified bridge configuration.

| Field | Type | Source |
|---|---|---|
| `strategy_id` | string | winning strategy |
| `strategy_version` | string | strategy catalog version |
| `prefix_identity` | string | normalized WINEPREFIX path hash |
| `prefix_architecture` | string | wine prefix arch |
| `windows_version` | string | `read_wine_windows_version()` |
| `winetricks_components` | list[str] | installed packages |
| `dll_overrides` | map[str,str] | relevant overrides |
| `environment_variables` | map[str,str] | stable launch env subset |
| `launch_wrapper_version` | string | ascension/electron wrapper build id |
| `remediation_protocol` | list[{id, version}] | ordered remediation ids used |
| `config_file_hashes` | map[str,str] | e.g. Ascension config, guard wrapper |

### VerificationBinding

Binds the profile to a specific verification outcome.

| Field | Type |
|---|---|
| `policy_id` | string (`bridge_aggregate_v1`) |
| `policy_version` | string |
| `verifier_ids` | list[str] |
| `verifier_versions` | list[str] |
| `required_checks` | list[str] |
| `persisted_evidence` | list[str] |
| `aggregate_confidence` | float |
| `verified_at` | ISO timestamp |
| `source_session_id` | UUID |
| `source_attempt_number` | int |

### ReuseConstraints

| Field | Type | Semantics |
|---|---|---|
| `exact_match_fields` | list[str] | must match exactly (e.g. `executable_hash`) |
| `compatible_ranges` | map | allowed version/runtime ranges |
| `host_differences_allowed` | list[str] | fields that may drift (e.g. kernel minor) |
| `required_capabilities` | list[str] | gpu, container, sudo, etc. |
| `prohibited_changes` | list[str] | fields that invalidate on any change |
| `max_profile_age_hours` | int | default 168 |
| `minimum_confidence` | float | eligibility floor |

### InvalidationRules

Hard invalidation triggers:

- `executable_hash` changed
- `product_version` changed materially
- Wine/Proton version changed
- prefix mutated outside Alma since verification
- verification policy changed materially
- verifier version changed for required checks
- required dependency version changed
- prior reuse failed verification
- fatal signature observed on reuse (`permission_denied`, `wine_int3_crash`, etc.)

---

## 2. Profile lifecycle states

```
CANDIDATE → VERIFIED → DEGRADED → INVALIDATED → RETIRED
```

| State | Meaning | Who may set | Evidence required |
|---|---|---|---|
| `CANDIDATE` | Created from a verified session, pending promotion review | `ProfileService` after `SUCCEEDED` | full `VerificationBinding` |
| `VERIFIED` | Eligible for reuse queries | `ProfileService` after binding validation | policy + checks persisted |
| `DEGRADED` | Reuse failed but not fatal; confidence reduced | `ProfileService` after failed reuse verification | reuse event + failure signature |
| `INVALIDATED` | Must not be reused | `ProfileService` / invalidation engine | rule id + evidence |
| `RETIRED` | Archived; kept for lineage only | operator or TTL job | retirement reason |

**Authority:** Only `ProfileService` (new module under `alma_bridge/compatibility/`) may change
profile state. It does **not** own bridge session lifecycle and does **not** call
`finalize_session(success=True)`.

---

## 3. Safe reuse flow

```
inspect program + host
  → calculate ProgramFingerprint + HostFingerprint
  → query eligible VERIFIED profiles
  → evaluate ReuseConstraints + InvalidationRules
  → rank eligible profiles (deterministic eligibility first, then confidence)
  → reconstruct BridgeFingerprint into planner input (strategy, env, remediations)
  → BridgeOrchestrator executes normally
  → VerificationEngine evaluates current execution
  → persist reuse event (success/fail/degrade/invalidate)
  → adjust profile confidence
```

**Invariant:** prior profile success never bypasses current verification.

---

## 4. Confidence semantics

Do not use a single opaque ML score. Maintain separate dimensions:

| Dimension | Meaning | Updated when |
|---|---|---|
| `evidence_confidence` | strength of original verification checks | profile creation |
| `environment_match_confidence` | host/program fingerprint match quality | each reuse query |
| `verification_confidence` | latest verification outcome on reuse | each reuse attempt |
| `reuse_success_rate` | successful reuses / total reuse attempts | reuse events |
| `recency_weight` | time-decay factor | query time |
| `failure_penalty` | accumulated degradation from failures | failed reuse |

### Ranking combination

1. **Eligibility gate (deterministic):** all `exact_match_fields`, `prohibited_changes`, age, and
   `minimum_confidence` must pass. Failing profiles are excluded entirely.
2. **Rank score (deterministic tie-breakers):**
   ```
   rank = (
     0.35 * environment_match_confidence
   + 0.30 * verification_confidence
   + 0.20 * reuse_success_rate
   + 0.10 * evidence_confidence
   + 0.05 * recency_weight
   ) - failure_penalty
   ```
3. Planner receives ranked profiles as **hints**; `BridgeOrchestrator` remains authoritative.

---

## 5. Persistence schema (additive SQLite)

### `compatibility_profiles`

| Column | Type | Index |
|---|---|---|
| `profile_id` | TEXT PK | PK |
| `state` | TEXT | yes |
| `created_at` | TEXT | |
| `updated_at` | TEXT | yes |
| `verified_at` | TEXT | yes |
| `source_session_id` | TEXT | |
| `executable_hash` | TEXT | yes |
| `normalized_path` | TEXT | |
| `program_kind` | TEXT | yes |
| `host_os_id` | TEXT | yes |
| `host_arch` | TEXT | yes |
| `strategy_id` | TEXT | yes |
| `prefix_identity` | TEXT | yes |
| `policy_id` | TEXT | |
| `policy_version` | TEXT | |
| `aggregate_confidence` | REAL | yes |
| `reuse_success_count` | INT | |
| `reuse_failure_count` | INT | |
| `evidence_json` | TEXT | extensible payload |

### `compatibility_profile_program_fingerprints`

`profile_id`, `executable_hash`, `file_size`, `architecture`, `product_version`, `bundled_hashes_json`

### `compatibility_profile_host_fingerprints`

`profile_id`, `os_id`, `os_version_id`, `kernel_version`, `host_arch`, `wine_version`, `gpu_identity`, `deps_json`

### `compatibility_profile_bridge_config`

`profile_id`, `strategy_id`, `prefix_identity`, `windows_version`, `winetricks_json`, `env_json`, `remediation_json`, `config_hashes_json`

### `compatibility_profile_verification`

`profile_id`, `policy_id`, `policy_version`, `verifier_ids_json`, `required_checks_json`, `evidence_json`, `confidence`, `verified_at`

### `compatibility_profile_reuse_events`

`event_id`, `profile_id`, `session_id`, `attempt_number`, `outcome`, `match_confidence`, `verification_passed`, `failure_signature`, `created_at`

### `compatibility_profile_invalidations`

`invalidation_id`, `profile_id`, `rule_id`, `reason`, `evidence_json`, `created_at`

---

## 6. Fingerprint algorithms

### Path normalization

```
expanduser → resolve → replace $HOME with "~" → lowercase on case-insensitive FS
```

### Program identity key

```
SHA-256(executable_hash + "|" + program_kind + "|" + architecture)
```

### Host identity key

```
SHA-256(os_id + "|" + os_version_id + "|" + host_arch + "|" + wine_version + "|" + gpu_identity)
```

### Bridge identity key

```
SHA-256(strategy_id + "|" + prefix_identity + "|" + windows_version + "|" + sorted remediation ids)
```

### Eligibility query (indexed)

```sql
SELECT * FROM compatibility_profiles
 WHERE state = 'VERIFIED'
   AND executable_hash = ?
   AND host_os_id = ?
   AND host_arch = ?
   AND aggregate_confidence >= ?
   AND verified_at >= datetime('now', ?)
 ORDER BY aggregate_confidence DESC, verified_at DESC
```

Post-query: apply `ReuseConstraints` and `InvalidationRules` in Python for complex checks.

---

## 7. First vertical slice (Ascension/Electron/Wine)

### Scenario

Ascension Launcher on Wine — already supported via installer + launcher handoff paths.

### First run (profile creation)

1. `/bridge/run` on Ascension installer with `launch_after_install=true`
2. Orchestrator remediates through ascension + electron chain
3. `VerificationEngine.verify_launcher()` passes with `process_survives`
4. Session reaches `SUCCEEDED` via `VerificationGateway`
5. `ProfileService.promote_from_session()` writes `CANDIDATE → VERIFIED` with full bindings

### Second run (reuse)

1. Same installer/host fingerprints match a `VERIFIED` profile
2. Planner receives profile-derived strategy/env/remediation ordering as hints
3. Orchestrator skips rediscovery where safe; still executes and verifies
4. Current `VerificationEngine` must pass
5. `compatibility_profile_reuse_events` records success; confidence increases

### Changed environment (invalidation)

1. Wine version or executable hash changes
2. Eligibility gate fails OR invalidation rule fires
3. Profile transitions to `INVALIDATED`
4. Orchestrator falls back to normal planning/remediation

---

## 8. Files to create/modify (future implementation)

### Create

- `alma_bridge/compatibility/profile_models.py` — dataclasses above
- `alma_bridge/compatibility/profile_service.py` — state transitions, persistence
- `alma_bridge/compatibility/profile_fingerprints.py` — fingerprint builders
- `alma_bridge/compatibility/profile_eligibility.py` — constraints + invalidation
- `alma_bridge/compatibility/profile_ranking.py` — deterministic ranking
- `alma_bridge/storage/profile_store.py` — SQLite CRUD + migrations
- `tests/test_compatibility_profile_*.py`

### Modify (minimal)

- `alma_bridge/session/services/planner.py` — accept optional profile hints (read-only)
- `alma_bridge/learning/orchestrator.py` — invoke `ProfileService` after verified success and before planning when profiles exist
- `alma_bridge/storage/outcomes.py` — migration hooks only
- **Do not** move lifecycle or verification authority into profile modules

---

## 9. Migration plan

1. Add SQLite tables (no breaking changes)
2. Promote profiles from new `SUCCEEDED` sessions only
3. Run reuse in shadow mode (log-only ranking) for one release
4. Enable reuse hints in planner behind feature flag
5. Deprecate `PrefixReadinessProfile` fast-path skip once profile reuse is stable

`PrefixReadinessProfile` remains until CompatibilityProfile covers its use case; no dual authority.

---

## 10. Security analysis

| Risk | Mitigation |
|---|---|
| Reuse of stale/broken config | invalidation rules + mandatory re-verification |
| Profile poisoning from false success | profiles only created from `SUCCEEDED` sessions with persisted `verification_json` |
| Cross-tenant prefix reuse | `prefix_identity` bound to executable hash + host fingerprint |
| Unguarded prefix replay | orchestrator still uses `run_prefix_mutation()` |
| Profile module becomes lifecycle owner | prohibited by ADR-001; static invariant tests |
| Opaque JSON-only storage | indexed columns for eligibility; JSON for evidence only |

---

## 11. Test matrix (future)

| Test | Type |
|---|---|
| Profile created only from verified session | behavioral |
| Reuse hint does not skip verification | behavioral |
| Hash change invalidates profile | unit |
| Wine version change invalidates profile | unit |
| Failed reuse degrades confidence | behavioral |
| ProfileService cannot call `finalize_session(True)` | static AST |
| ProfileService cannot transition session state | static AST |
| Prior profile does not produce `SUCCEEDED` without `VERIFYING` | behavioral |
| Ranking is deterministic for same inputs | unit |
| Ascension vertical slice first-run → second-run → invalidation | integration |

---

## 12. Explicit non-goals

- CompatibilityProfile is **not** a planner
- CompatibilityProfile is **not** a lifecycle owner
- CompatibilityProfile does **not** replace `VerificationEngine`
- CompatibilityProfile does **not** bypass `PolicyGate` or `prefix_lock`
- No implementation until this design is approved

---

## 13. Design review revisions (2026-07-13)

The sections below supersede or extend earlier sections where they conflict. Unchanged
material above remains valid unless explicitly revised here.

### 13.1 Profile identity, lineage, and revision rules

#### Three-level identity model

| Concept | Definition | Stable across |
|---|---|---|
| `profile_id` | UUID primary key for one persisted row | lifetime of row |
| `profile_lineage_key` | Deterministic dedup key for one logical solution | revisions; not timestamps |
| `profile_revision` | Monotonic integer (`row_version`) per `profile_id` | optimistic concurrency |

**Same logical profile** = same `profile_lineage_key`.  
**Same profile row** = same `profile_id`.  
**Same reusable binding** = same `profile_id` + `profile_revision` + compatible `verification_binding_key`.

#### `profile_lineage_key` composition (identity-critical only)

```
SHA-256-v1(
  program_identity_key
  + host_compatibility_class_id
  + bridge_recipe_key
  + verification_binding_key
)
```

| Component | Inputs | Notes |
|---|---|---|
| `program_identity_key` | `executable_hash`, `program_kind`, `architecture`, normalized `product_version` | **Not** `normalized_path`, **not** timestamps |
| `host_compatibility_class_id` | deterministic host class (§13.3) | **Not** exact kernel string or hostname |
| `bridge_recipe_key` | `strategy_id`, sorted remediation protocol `(id, version)` pairs, `bridge_manifest_hash` | **Not** mutable prefix path |
| `verification_binding_key` | `policy_id`, `policy_version`, sorted required `check_kind` list | binds trust to verification contract |

`program_fingerprint` (name-token hash from `compute_program_fingerprint()`) is used for
**similar-program discovery** and ranking, not for lineage identity. Two binaries with
different `executable_hash` but same product lineage may share ranking hints but never
share a lineage key unless explicitly linked by product version rules.

#### What each change produces

| Change | Outcome |
|---|---|
| New remediation/env/component in manifest | **New `profile_revision`** on same `profile_id` (or new row if recipe key changes) |
| `executable_hash` change | **New profile** (new `profile_lineage_key`) |
| Material `product_version` change | **New profile** |
| Same binary, compatible host class drift (kernel minor) | **Reuse event only**; may reduce `environment_match_confidence` |
| Same binary, incompatible host class (Wine major change) | **Eligibility rejection**; optional **scoped invalidation** for that host class |
| Prefix drift detected vs manifest | **Reuse event** + possible **scoped invalidation** (`bridge_revision` scope) |
| Verification policy minor bump, same required checks | **Re-verification required** on reuse; profile remains eligible |
| Verification policy material change / new required check | **Scoped invalidation** of `verifier_binding` or whole profile |
| Failed reuse on one host | **Reuse event** + confidence penalty; **not** global invalidation by default |
| Operator manual edit | **Trust demotion** + optional **scoped invalidation** |

#### Deduplication on creation

```sql
UNIQUE(profile_lineage_key, profile_revision)
```

Creation uses `INSERT ... ON CONFLICT DO NOTHING` then `SELECT`. Concurrent creators
converge on one row. Timestamps never appear in lineage keys.

---

### 13.2 Fingerprint field classification and canonical serialization

**Schema version:** `fingerprint_schema_v1`  
**Hash algorithm:** `SHA-256` over UTF-8 canonical JSON  
**Canonical JSON rules:**
- keys sorted lexicographically at all object levels
- arrays that represent sets: sorted lexicographically
- `null` explicit for missing optional fields (never omit keys in identity payloads)
- numbers: integers as JSON integers; floats rounded to 6 decimal places in ranking-only fields
- strings: NFC Unicode normalization
- paths: normalized per §6 path rules; stored as `~`-relative where under `$HOME`
- env maps: sorted keys, values as strings, exclude ephemeral vars (`$`, `PWD`, `SHLVL`, `OLDPWD`, `_`, session-scoped temp)

#### Program fields

| Field | Class |
|---|---|
| `executable_hash` | identity-critical |
| `program_kind` | identity-critical |
| `architecture` | identity-critical |
| `product_version` (normalized) | identity-critical |
| `executable_format` | compatibility-critical |
| `file_size` | compatibility-critical |
| `product_name` | ranking-only |
| `normalized_path` | audit-only |
| `bundled_file_hashes` | compatibility-critical (selected keys only) |
| `program_fingerprint` (name tokens) | ranking-only |

#### Host fields

| Field | Class |
|---|---|
| `host_compatibility_class_id` | identity-critical |
| `os_id` / `os_version_id` | compatibility-critical (class inputs) |
| `host_arch` | identity-critical |
| `wine_major` / `proton_family` | compatibility-critical |
| `capability_set` | compatibility-critical |
| `gpu_class` | compatibility-critical when `program.needs_gpu`; else audit-only |
| `kernel_version` | ranking-only (min version checked separately) |
| `dependency_versions` | compatibility-critical (subset: dotnet, vcrun, winetricks core) |
| `container_capable` | compatibility-critical |
| hostname, PID, temp paths | **excluded** |

#### Bridge fields

| Field | Class |
|---|---|
| `bridge_manifest_hash` | identity-critical |
| `strategy_id`, `strategy_version` | identity-critical |
| `remediation_protocol` `(id, version)` | identity-critical |
| `windows_version`, `prefix_architecture` | compatibility-critical |
| `winetricks_components`, `dll_overrides`, `env` (stable subset) | compatibility-critical |
| `config_file_hashes`, `wrapper_versions` | compatibility-critical |
| `prefix_identity` (path hash) | audit-only hint only |
| `prefix_reference` | audit-only |

#### Verification fields

| Field | Class |
|---|---|
| `policy_id`, `policy_version` | identity-critical |
| `required_checks` | identity-critical |
| `verifier_ids`, `verifier_versions` | compatibility-critical |
| `persisted_evidence` | audit-only |
| `verified_at`, `source_session_id` | audit-only |

---

### 13.3 Host compatibility classes

A **host compatibility class** is a deterministic bucket, not an exact host fingerprint.

```
host_compatibility_class_id = SHA-256-v1({
  "schema": "host_class_v1",
  "os_family": <ID or first ID_LIKE token>,
  "host_arch": <x86_64|aarch64|...>,
  "wine_major": <major version or null>,
  "proton_family": <catalog id or null>,
  "capability_set": <sorted required capabilities>,
  "gpu_class": <none|software|vendor:driver_major>  // only if program requires GPU
})
```

#### Difference handling

| Difference | Effect |
|---|---|
| Different `os_family` | **Prohibits reuse** |
| Different `host_arch` | **Prohibits reuse** |
| Wine major version mismatch | **Prohibits reuse** for Wine profiles |
| Wine minor/patch drift | **Reduces ranking confidence** only |
| Kernel newer than profile `kernel_minimum` | **Reuse event**; no penalty |
| Kernel older than minimum | **Eligibility rejection** |
| Missing required capability (container, sudo) | **Prohibits reuse** |
| GPU class mismatch on GPU-sensitive program | **Prohibits reuse** |
| GPU class mismatch on non-GPU program | **Irrelevant** |
| Same class, different `os_version_id` | **Reduces `environment_match_confidence`** |

Reuse queries filter by `host_compatibility_class_id`, not exact host fingerprint.

---

### 13.4 Bridge reconstruction and drift detection

A profile stores a **reproducible bridge recipe (manifest)**. It may optionally record a
**prefix reference hint** for performance. It does **not** store an opaque snapshot/image as
the authoritative source of truth.

#### Minimum reproducible bridge manifest

| Manifest section | Required content |
|---|---|
| `base_runtime` | `wine` \| `proton` \| `native`; version/family |
| `prefix_architecture` | wine prefix arch |
| `windows_version` | e.g. `win10` |
| `installed_components` | winetricks packages, dotnet/vcrun markers |
| `dll_overrides` | normalized map |
| `environment` | stable launch env subset (canonical sorted) |
| `wrapper_versions` | ascension/electron wrapper build ids |
| `remediation_protocol` | ordered `(id, version)` list |
| `config_file_hashes` | launcher/guard/config hashes |
| `file_hashes` | installed launcher path template + hash |
| `external_artifacts` | §13.10 provenance records |

```
bridge_manifest_hash = SHA-256-v1(canonical_json(manifest))
bridge_recipe_key = SHA-256-v1(strategy_id + remediation_protocol + bridge_manifest_hash)
```

#### Prefix reference (non-authoritative)

- `prefix_reference`: normalized path at verification time — **audit-only**
- Reuse **never** assumes the prefix is unchanged because the path matches
- Reuse workflow: reconstruct recipe → apply via `PolicyGate` + `run_prefix_mutation()` →
  drift check → execute → verify

#### Drift detection

Before execution, `ProfileService` snapshots the live prefix and compares to manifest:

| Signal | Action |
|---|---|
| Missing required component | **Eligibility rejection** or scoped `bridge_revision` invalidation |
| Unexpected DLL override change | **Reuse event** + degrade confidence |
| `config_file_hashes` mismatch | **Eligibility rejection** |
| Launcher hash mismatch | **Eligibility rejection** |
| External mutation marker (mtime outside Alma) | **Scoped invalidation** `bridge_revision` |

Drift checks produce a structured `reconstruction_result` on every reuse attempt.

---

### 13.5 Trust model (separate from lifecycle state)

Lifecycle (`CANDIDATE`, `VERIFIED`, `DEGRADED`, `INVALIDATED`, `RETIRED`) is orthogonal to trust.

| Trust state | Meaning | Max reuse rank cap |
|---|---|---|
| `locally_verified` | Created from Alma `SUCCEEDED` session with persisted `verification_json` | 1.0 |
| `reconstructed` | Manifest replayed successfully on reuse before execution | 0.95 |
| `reused_successfully` | ≥1 reuse passed current `VerificationEngine` | 1.0 |
| `reused_with_degradation` | Reuse passed but drift/degraded confidence observed | 0.8 |
| `imported` | External origin; not Alma-verified at creation | 0.5 |
| `manually_modified` | Operator edited manifest or constraints | 0.3 |
| `invalidated` | Scoped or global invalidation active | 0.0 (ineligible) |

**Rules:**
- `imported` and `manually_modified` profiles cannot auto-promote to `locally_verified`
- Active reuse requires `trust_state ∈ {locally_verified, reconstructed, reused_successfully}`
- `imported` profiles may only run in **shadow mode** until locally re-verified

---

### 13.6 Verification compatibility matrix

Current `VerificationEngine` is always authoritative on every run.

| Change | Action |
|---|---|
| `policy_id` change | **Immediate scoped invalidation** (`verifier_binding`) |
| `policy_version` bump, same required checks | **Re-verification on reuse**; profile stays eligible |
| New required `check_kind` | **Scoped invalidation** unless profile already has matching evidence |
| Verifier version bump, same semantics | **Re-verification**; reduce confidence 0.1 until passed |
| Verifier version bump, semantic change | **Scoped invalidation** (`verifier_binding`) |
| `minimum_confidence` threshold raised | **Eligibility rejection** for low-confidence profiles; not invalidation |
| Optional check becomes required | **Scoped invalidation** of profiles missing that evidence |

Reuse always runs the **current** policy via `VerificationEngine`; stored binding is metadata
for eligibility, not a bypass.

---

### 13.7 Scoped invalidation model

Invalidation is **never global by default** for a single-host reuse failure.

#### Invalidation scopes

| Scope | Affects | Example |
|---|---|---|
| `profile` | entire row | executable hash obsolete |
| `host_class` | `profile_id` + `host_compatibility_class_id` | Wine major mismatch on one machine |
| `bridge_revision` | `profile_id` + `profile_revision` | manifest drift |
| `verifier_binding` | `profile_id` + `policy_id` + `policy_version` | policy material change |
| `reuse_candidate` | single reuse attempt | unrelated runtime failure |

#### `compatibility_profile_invalidations` (revised)

| Column | Purpose |
|---|---|
| `invalidation_id` | PK |
| `profile_id` | FK |
| `scope` | `profile` \| `host_class` \| `bridge_revision` \| `verifier_binding` \| `reuse_candidate` |
| `scope_key` | deterministic key for scoped dimension |
| `rule_id` | machine-readable rule |
| `reason` | human-readable |
| `evidence_json` | structured evidence |
| `created_at` | audit |
| `active` | bool; allows lifting operator overrides |

Eligibility query excludes rows with active invalidation matching the query dimensions.

---

### 13.8 Failure learning (reuse events revised)

Every reuse attempt persists a full `compatibility_profile_reuse_events` row:

| Field | Content |
|---|---|
| `profile_id`, `profile_revision` | matched profile |
| `host_compatibility_class_id` | query-time class |
| `eligibility_decision` | `eligible` \| `rejected` + reason codes |
| `ranking_components_json` | all confidence dimensions + final rank |
| `reconstruction_result` | `ok` \| `drift_detected` \| `failed` + details |
| `execution_evidence_ref` | attempt id / phase |
| `verification_result_json` | full current verification outcome |
| `failure_signature` | if failed |
| `failure_class` | `drift` \| `environment_mismatch` \| `profile_defect` \| `runtime_unrelated` |
| `shadow_mode` | bool |

#### Repeated failure effects

| Pattern | Profile state | Host-class | Confidence |
|---|---|---|---|
| 1 unrelated runtime failure | unchanged | unchanged | `failure_penalty += 0.05` |
| 2+ `runtime_unrelated` | unchanged | unchanged | cap rank lower |
| 1 `drift` failure | `DEGRADED` | unchanged | `environment_match_confidence -= 0.15` |
| 2+ `drift` on same revision | scoped `bridge_revision` invalidation | unchanged | revision retired |
| 1 `environment_mismatch` | unchanged | scoped `host_class` invalidation | n/a |
| 3+ `profile_defect` verification failures | `INVALIDATED` (`profile` scope) | may also scope host | retirement candidate |
| 5+ failures with 0 successes | `RETIRED` | — | kept for audit |

---

### 13.9 Profile concurrency

| Scenario | Mechanism |
|---|---|
| Two sessions create same profile | `UNIQUE(profile_lineage_key, profile_revision)` + `ON CONFLICT DO NOTHING`; second reads existing row |
| Confidence update vs invalidation race | `row_version` optimistic locking: `UPDATE ... WHERE row_version = ?`; loser retries read |
| Two sessions reuse same mutable prefix | existing `prefix_lock` + `SessionLeaseManager`; profile code never bypasses |
| Retirement during active reuse | reuse loads `profile_id` + `row_version` at start; if retired before execution, abort reuse hint and fall back to normal planning |
| Lifecycle advancement | only `BridgeOrchestrator` with session lease may run bridge; profile service is read-only during execution |

#### Revised `compatibility_profiles` columns

Add: `profile_lineage_key`, `profile_revision`, `row_version`, `host_compatibility_class_id`,
`bridge_manifest_hash`, `bridge_recipe_key`, `verification_binding_key`, `trust_state`,
`kernel_minimum`, `schema_version`.

```sql
UNIQUE(profile_lineage_key, profile_revision)
INDEX(state, executable_hash, host_compatibility_class_id)
INDEX(profile_lineage_key)
```

---

### 13.10 Security and supply chain

#### `compatibility_profile_artifacts` (new table)

| Column | Content |
|---|---|
| `artifact_id` | PK |
| `profile_id` | FK |
| `artifact_type` | `wine_runtime`, `proton_distro`, `wrapper_binary`, `winetricks_package`, `config_file` |
| `name` | canonical name |
| `version` | semver or catalog version |
| `source` | `system`, `winetricks`, `alma_build`, `installed_launcher` |
| `acquisition_method` | `package_manager`, `winetricks`, `alma_compilation`, `installer_extracted` |
| `checksum_sha256` | required |
| `signature_status` | `unsigned`, `hash_verified`, `pgp_verified`, `unknown` |
| `path_template` | relative/template path, not absolute session path |

**Rules:**
- Profile reconstruction emits `ActionIntent` objects only; no raw shell from stored JSON
- All mutations pass `PolicyGate` + `run_prefix_mutation()`
- `imported` artifacts without checksum are ineligible for active reuse
- No arbitrary downloaded artifacts without checksum + allowlisted source

---

### 13.11 Data retention

| Data | Retention | GC |
|---|---|---|
| Reuse events | 90 days online; archive 1 year | partition by month |
| Verification evidence (audit copy) | life of profile + 1 year after retirement | never delete if sole audit of autonomous decision |
| Invalidation records | permanent | audit |
| Active profiles per `program_identity_key` | max 5 `VERIFIED` rows | dedupe by `profile_lineage_key`; retire lowest rank |
| `INVALIDATED` profiles | 180 days then `RETIRED` | keep row, clear manifest secrets |
| `RETIRED` profiles | permanent metadata; manifest may be truncated | evidence refs remain |

Deduplication: only one active `VERIFIED` row per `profile_lineage_key` at highest
`profile_revision` unless A/B testing flag enabled.

---

### 13.12 First vertical slice acceptance criteria (Ascension/Electron/Wine)

#### First run — must

- [ ] Exactly **one** `profile_id` created with `trust_state=locally_verified`
- [ ] `profile_lineage_key` includes ascension remediation protocol + electron launcher checks
- [ ] `bridge_manifest_hash` persisted with wrapper versions, winetricks components, env, launcher hash
- [ ] `verification_binding_key` = `bridge_aggregate_v1` + required `process_survives`
- [ ] `remediation_protocol` lists applied ascension + electron ids in order
- [ ] No duplicate row on immediate re-ingest of same session

#### Second run — must

- [ ] Eligibility matches by `executable_hash` + `host_compatibility_class_id`
- [ ] `reconstruction_result.ok = true` before execution
- [ ] Orchestrator passes through full lifecycle including `VERIFYING`
- [ ] Current `VerificationEngine` passes
- [ ] Reuse event persisted with `failure_class` null
- [ ] `trust_state` → `reused_successfully`
- [ ] No second `profile_id` for same `profile_lineage_key`

#### Changed environment — must

- [ ] Wine major bump → `eligibility_decision=rejected`, reason `wine_major_mismatch`
- [ ] Executable hash change → no match; normal planning; original profile untouched
- [ ] Scoped `host_class` invalidation recorded when reuse attempted on wrong class
- [ ] Shadow and active modes produce identical eligibility decision

---

### 13.13 Rollout strategy and feature flags

| Flag | Default | Effect |
|---|---|---|
| `compatibility_profiles_enabled` | `false` | master gate |
| `compatibility_profile_creation_enabled` | `false` | promote profiles after `SUCCEEDED` |
| `compatibility_profile_reuse_enabled` | `false` | planner receives profile hints |
| `compatibility_profile_shadow_mode` | `true` when profiles enabled | match/rank/eligibility logged only |

#### Shadow mode flow

```
planning phase:
  compute fingerprints → query profiles → eligibility → rank
  log shadow_match, shadow_rank, shadow_eligibility_reason
  DO NOT alter planner output
after normal run completes:
  compare shadow winner vs actual winning strategy/remediation
  emit shadow_accuracy metric
```

#### Promotion metrics (active reuse gate)

| Metric | Threshold |
|---|---|
| Shadow eligibility precision | ≥ 0.95 over 50 runs |
| Shadow rank top-1 agreement | ≥ 0.80 |
| Active reuse verification pass rate | ≥ 0.90 over 20 reuses |
| Drift false-positive rate | ≤ 0.05 |
| Duplicate profile creation rate | 0 |

---

### 13.14 Observability

| Metric / log field | Type |
|---|---|
| `profile.candidates_created` | counter |
| `profile.verified` | counter |
| `profile.matches` | counter by `program_identity_key` |
| `profile.eligibility_rejected` | counter by `reason` |
| `profile.shadow_predicted_match` | counter |
| `profile.reuse_attempts` | counter |
| `profile.reuse_verification_pass_rate` | gauge |
| `profile.reuse_fallback_rate` | gauge |
| `profile.invalidations` | counter by `scope` |
| `profile.bridge_drift_detected` | counter |
| `profile.duplicate_prevented` | counter |
| `profile.reuse_event` | structured log per attempt |

---

### 13.15 Implementation gate — first-slice tests (exact)

| ID | Test | Pass criteria |
|---|---|---|
| CP-01 | `test_profile_created_only_from_verified_session` | no profile if `VERIFYING` not in transition history |
| CP-02 | `test_lineage_key_excludes_timestamps_and_absolute_paths` | same inputs → same key across runs |
| CP-03 | `test_dedup_concurrent_creation` | two parallel creates → one row |
| CP-04 | `test_host_class_wine_major_mismatch_rejects` | eligibility `rejected` |
| CP-05 | `test_host_class_kernel_minor_allows_reuse` | eligible; confidence reduced |
| CP-06 | `test_bridge_manifest_drift_blocks_reuse` | `reconstruction_result=drift_detected` |
| CP-07 | `test_scoped_host_class_invalidation_not_global` | profile still eligible on original class |
| CP-08 | `test_verification_policy_minor_bump_requires_reverify` | eligible; must pass current engine |
| CP-09 | `test_imported_profile_cannot_active_reuse` | shadow only |
| CP-10 | `test_reuse_does_not_finalize_session_without_verifying` | architectural invariant |
| CP-11 | `test_ascension_first_run_creates_manifest` | integration |
| CP-12 | `test_ascension_second_run_reuses_without_duplicate` | integration |
| CP-13 | `test_ascension_wine_major_change_rejects_reuse` | integration |
| CP-14 | `test_shadow_mode_does_not_change_planner_output` | shadow |
| CP-15 | `test_profile_service_never_calls_finalize_success` | static AST |

**Implementation blocked until:** Phase 1 complete and Phase 2 explicitly approved.

---

## 13.16 Phase 1 implementation (complete)

### ProfileCandidateSnapshot flow

```
execution → verification → persist VerificationResult
  → build ProfileCandidateSnapshot from verified attempt + bridge state
  → persist ProfileCandidateSnapshot
  → VerificationGateway declares session success → SUCCEEDED
  → ProfileCreationService promotes persisted candidate (by candidate_id or snapshot)
```

Candidate persistence failure does **not** block `SUCCEEDED`. Profile creation is skipped;
`compatibility_profile_candidate_events` and `profile_candidate_persist_failed` metric are emitted.

`ProfileCreationService` accepts `candidate_id` or loaded `ProfileCandidateSnapshot` only — never
`BridgeRequest`, mutable attempts, hardware probes, or live prefix state.

### bridge_family_key canonical payload (`bridge_family_v1`)

```json
{
  "schema": "bridge_family_v1",
  "strategy_id": "<strategy>",
  "runtime_family": "wine|proton|native|unknown",
  "program_kind": "<classify_program_kind>",
  "protocol_family": "installer|electron_launcher|generic",
  "bridge_architecture_class": "<runtime>_<format>_<kind>"
}
```

SHA-256 of canonical JSON. Does **not** include manifest hash, env, remediation versions, or paths.

### Lineage / revision / idempotency

| Key | Formula |
|---|---|
| `profile_lineage_key` | `sha256(program_identity_key + host_compatibility_class_id + bridge_family_key + verification_binding_key)` |
| `profile_revision` | Atomic increment per `profile_lineage_key` when `bridge_manifest_hash` changes |
| `idempotency_key` | `sha256(profile_lineage_key + bridge_manifest_hash + verification_binding_key)` |

Same family + changed manifest → same lineage, new revision. Changed family → new lineage.
Same manifest → attach verification evidence, no new revision.

### Verification attachment idempotency

`UNIQUE(profile_id, session_id, attempt_number, attachment_reason)` plus deterministic
`attachment_idempotency_key`. Creation events use `UNIQUE(idempotency_key, outcome)`.

### Feature flags (Phase 1)

| Flag | Default |
|---|---|
| `compatibility_profiles_enabled` | `false` |
| `compatibility_profile_creation_enabled` | `false` |

---

## 13.17 Phase 2 design correction — immutable shadow observations (NOT IMPLEMENTED)

Do **not** overwrite prediction rows with actual results.

### ShadowPrediction (persisted before normal planner execution)

Immutable fields: `shadow_event_id`, `session_id`, candidate profile IDs/revisions,
eligibility decision per candidate, eligibility reason codes, invalidation filters applied,
ranking component inputs, ranking formula/version, selected predicted profile,
predicted strategy, predicted remediation protocols, predicted drift result,
host compatibility class, timestamp.

### ShadowActualOutcome (persisted after run completes)

Immutable fields: `shadow_event_id`, actual strategy, actual remediation,
execution result reference, verification result reference, session outcome, `completed_at`.

Comparison metrics are derived from immutable prediction + immutable actual outcome pairs.
Prediction fields are never updated post-run.

---

## 13.18 Phase 2 implementation (shadow mode — complete)

Shadow mode is observe-only. It does not alter planner output, execution plans, lifecycle, prefix state, or `BridgeSessionResult.success`.

### Feature flag

`compatibility_profile_shadow_mode` (default `false`) runs only when `compatibility_profiles_enabled` is also `true`.

### Orchestrator hooks

| Hook | Location | Action |
|---|---|---|
| Pre-planning | `_run_session()` before `_planner.plan()` | `ProfileShadowService.create_prediction()` |
| Pre-planning | `_run_launcher_handoff()` before `build_execution_plan()` | same |
| Post-terminal | `run()` after `_run_session()` returns | `ProfileShadowService.record_actual_outcome()` |

Failures in either hook are swallowed; Bridge execution continues unchanged.

### Ranking formula

`profile_shadow_rank_v1` / `1.0.0` with explicit components: program identity match, host-class match, bridge-family match, environment-match confidence, verification confidence, trust-state cap, reuse success rate, recency, failure penalty, drift penalty, optional ML component (bounded 0–0.15).

### Tables

`compatibility_profile_shadow_predictions`, `compatibility_profile_shadow_candidates`, `compatibility_profile_shadow_actual_outcomes`, `compatibility_profile_shadow_comparisons`, `compatibility_profile_shadow_events`.

---

## 13.19 Shadow validation and promotion readiness (complete)

Read-only validation tooling for promotion gate evaluation. Does not implement active reuse.

### CLI

`alma-bridge-shadow-validation report|gates|sync-manifest|register-run|add-label|analyze-failures|export`

### API

`GET /compatibility/shadow/validation/report`, `GET /compatibility/shadow/validation/gates`

### Validation schema

`compatibility_profile_shadow_scenarios`, `compatibility_profile_shadow_validation_runs`, `compatibility_profile_shadow_labels`, `compatibility_profile_shadow_failure_analysis`

Manifest: `data/validation/shadow_scenario_manifest_v1.json` (categories A–J)

---

