# Alma Bridge Development Progress Overview

**Last updated:** 2026-07-14  
**Scope:** CompatibilityProfile Phase 2 shadow mode through verified Code::Blocks launch  
**Audience:** Technical operators and non-technical stakeholders

---

## How to read this document

Alma Bridge runs Windows applications on Linux through Wine. The **CompatibilityProfile** subsystem learns from successful runs but, by design, does **not** yet control execution. This overview walks through ten chronological stages: what was built, what broke, what was fixed, and what is proven today versus still under validation.

**Key constraint throughout:** active profile reuse remains **disabled** (`ALMA_BRIDGE_COMPATIBILITY_PROFILE_REUSE_ENABLED=false`). Shadow mode is observe-only.

---

## 1. CompatibilityProfile Phase 2

**What it is (plain language):** After Alma successfully runs an app, it can save a “recipe” (profile) describing what worked. Phase 2 adds a **shadow observer** that predicts which saved recipe *would* have been chosen — without actually using it — and compares that prediction to what really happened.

**Technical summary:**

| Capability | Behavior |
|------------|----------|
| Shadow predictions | Immutable, created **before** planning; never applied to execution |
| Eligibility & ranking | Deterministic rejection reason codes; `profile_shadow_rank_v1` scoring |
| Drift detection | Host overlay, Windows version, component, trust-state dimensions |
| Actual-outcome comparison | Post-run metrics persisted for offline gate evaluation |
| Active reuse | **Deliberately disabled** behind feature flag and promotion gates |

**Architecture references:**

- Design: `docs/design/compatibility-profile-design.md`
- Architecture review: `docs/reviews/compatibility-profile-architecture-review.md`
- Lifecycle authority: `docs/adr/ADR-001-authoritative-bridge-lifecycle.md`

**Data flow:** `BridgeOrchestrator` → shadow prediction (observe only) → plan/execute/verify → profile candidate on verified success → actual outcome + comparison at finalize. See architecture review § “Data flow.”

---

## 2. Shadow Validation Infrastructure

Before any decision to enable active reuse, Alma built a formal validation pipeline to collect and score shadow evidence.

| Component | Purpose | Artifact |
|-----------|---------|----------|
| Scenario manifests | Frozen A–J matrix (stable success, drift, trust, ranking, etc.) | `data/validation/campaigns/shadow-validation-pilot-*.json` |
| Operator labels | Human rubric labels (`rejected_correct`, `drift_correct`, …) | `alma-bridge-shadow-validation label-run` |
| Failure analysis | Structured post-mortems on mispredictions | `compatibility_profile_shadow_failure_analysis` table |
| Promotion gates | Quantitative thresholds (≥50 comparisons, precision ≥0.95, …) | `alma-bridge-shadow-validation gates` |
| Sanitized evidence exports | Redacted, append-only campaign artifacts | `data/validation/evidence/pilot-*/` |
| Operational runbook | Environment prep, disposable prefixes, registration workflow | `docs/operations/shadow-validation-runbook.md` |

**Operator workflow (abbreviated):** enable shadow flags → backup `outcomes.db` → run scenario via `/bridge/run` → register run → label → export evidence → evaluate gates with `--campaign-id`.

---

## 3. Pilot-001 — Initial Campaign & Runaway Defects

**Status:** `exploratory_non_promotable` — excluded from promotion-gate calculations  
**Manifest:** `data/validation/campaigns/shadow-validation-pilot-001.json`

Pilot-001 was the first end-to-end shadow validation attempt. It surfaced serious lifecycle and prefix-safety defects before meaningful promotion evidence could be collected.

### What happened

| Issue | Detail |
|-------|--------|
| Runaway retry loop | Session `25238bf2-8ea4-4dc6-9d07-01f8255ef24d` reached **622 attempts** in an `invalid_launch_args` loop before operator termination (`OPERATOR_TERMINATED_RUNAWAY_SESSION`) |
| Primary prefix mutation | Production Ascension prefix was modified during validation; disposable-prefix discipline was not yet enforced |
| Lifecycle defect | Illegal `CLASSIFYING→EXECUTING` transition (Run 8, session `76b7e6dc-5e70-4ca0-9d79-4c76358ff015`) |
| Ascension sidecar failures | Runs against nested Ascension build failed with `sidecar_silent_crash` — not usable as verified baseline |

### Outcome

Closed as **non-promotable exploratory** evidence. Decision codes: `PRIMARY_PREFIX_MUTATED`, `LIFECYCLE_ROUTE_LOOP_DEFECT`, `VERIFIED_PROFILE_SEED_UNAVAILABLE`. Evidence preserved under `data/validation/evidence/pilot-001/`.

---

## 4. Corrective Engineering

**Commit:** `9d2a2ac` — `fix: bound auto-compatibility and harden validation lifecycle`  
**Reference:** `data/validation/campaigns/pilot-002-completion-gate.md` §1

Pilot-001 defects drove targeted hardening before any successor campaign:

| Fix | Module / behavior |
|-----|-------------------|
| **AutoCompatibilityBudget** | Session-scoped budget stops runaway escalation loops | `alma_bridge/session/auto_compat_budget.py` |
| **Lifecycle retry corrections** | Illegal state transitions blocked in route retry paths | `alma_bridge/learning/orchestrator.py` |
| **Terminal observation boundary** | Shadow actual outcomes recorded on all terminal paths | `tests/test_terminal_observation.py` |
| **Campaign safety guards** | Validation campaigns require disposable prefixes; block primary prefix mutation | `alma_bridge/validation/campaign_guard.py` |
| **Disposable-prefix requirements** | Enforced via `ALMA_BRIDGE_VALIDATION_CAMPAIGN_MODE` |

**Test coverage at corrective commit:** 527 passed (per `pilot-002-completion-gate.md`). New tests: `test_auto_compat_budget.py`, `test_auto_compat_lifecycle.py`, `test_campaign_guard.py`, `test_terminal_observation.py`.

---

## 5. Ascension Investigation

**Status:** Moved to **research workstream** — no compatibility success claim  
**Research note:** `data/validation/research/ascension-nested-sidecar-token-attestation.md`

Ascension (an Electron game launcher) was the original high-value target but blocked by a Wine-specific attestation problem, not by shadow-profile logic.

### Root finding

The nested Ascension build invokes `AscensionClientServices.real.exe`, which requires:

1. A live launcher PID and Windows image name match
2. A one-time `--token` from the Electron launcher

Alma’s decoy launcher satisfies PID/name survival but **cannot participate in token attestation**. Sidecar exits silently (`sidecar_silent_crash`); verification correctly never reaches `SUCCEEDED`.

### Classification

`ASCENSION_NESTED_SIDECAR_TOKEN_ATTESTATION_BLOCKED_UNDER_WINE`

Nested build SHA-256 `6b76d81a…` and flat build `cfed7563…` are **separate program identities** and must not be merged.

### Policy

No Ascension profile promotion until token attestation contract is documented and reproduced with a live Electron launcher — not decoy-only. General shadow validation may proceed on non-Ascension programs independently.

---

## 6. Pilot-002 and Pilot-003

Both campaigns exercised Wine GUI verification and manifest identity fixes but were **aborted** and excluded from promotion evidence.

### Shared engineering (Pilot-002 prep)

Documented in `data/validation/campaigns/pilot-002-wine-gui-completion-gate.md`:

- **`pe_windows_gui` classification** — ordinary GUI apps (Notepad, WordPad) distinct from Electron launchers
- **`wine_gui` execution phase** — detach, observe target PID, survival window
- **Verification contract** — `wine_gui_process_v1`: required check `process_survives`, optional `target_process_identity`
- **PE subsystem fix** — corrected PE32+ optional-header offset for GUI detection

### Pilot-002

| Field | Value |
|-------|-------|
| Status | `aborted_non_promotable` |
| Abort reason | `SCENARIO_ID_MANIFEST_MISMATCH` |
| Detail | Run 6 used `E_prefix_drift`; manifest defines `E_prefix_drift_windows` / `E_prefix_drift_component` only |
| Completed runs | 1–6 (Run 6 unregistered) |
| Closure | `data/validation/campaigns/shadow-validation-pilot-002-closure.json` |
| Gate policy | `exclude_from_gate_calculations: true` |

### Pilot-003

| Field | Value |
|-------|-------|
| Status | `aborted_non_promotable` |
| Abort reason | `INVALID_LABEL_TYPE` (Run 11 used `shadow_observation_only` — a trust category, not a rubric label) |
| Secondary defects | Post-hoc host overlay, drift not induced, known-failure scenario succeeded, candidate provenance mismatch |
| Completed runs | 1–11 of 13 planned |
| Closure | `data/validation/campaigns/shadow-validation-pilot-003-closure.json` |
| Gate policy | `exclude_from_gate_calculations: true` |

**Why excluded:** Operational and semantic defects invalidated runs as promotion evidence, though exploratory findings (T2 stable selection, relocated identity, shadow-only reconstruction) informed Pilot-004 corrective design.

---

## 7. Pilot-004

**Status:** `COMPLETED_NOT_PROMOTION_READY`  
**Freeze commit:** `6261d47`  
**Evidence quality review:** `data/validation/campaigns/pilot-004-evidence-quality-review.json`

Pilot-004 was the first campaign to complete all **13 scenarios** with corrected semantics.

### Scenarios exercised

| Scenario | What it validated |
|----------|-------------------|
| A — stable repeat success | Repeatable shadow prediction on verified profile |
| B — relocated executable | Path-free identity preserved across move |
| C/D — host drift | Compatible vs incompatible host overlay **pre-plan** |
| E — prefix drift (windows / component) | `WINDOWS_VERSION_DRIFT`, component missing detection |
| F — clean prefix reconstruction | Shadow-only; active reuse disabled |
| G — known compatibility failure | Exploratory only (Run 9 — API bypass) |
| H — unrelated runtime failure | Evidence persistence recovery (Run 10) |
| I — trust state | Imported and invalidated profile exclusion |
| J — multiple candidate ranking | Deterministic ranking between two eligible candidates |

### Evidence quality (12 promotion-eligible runs)

| Run | Scenario | Session ID |
|-----|----------|------------|
| 1 | A_stable_repeat_success | `4bd166cf-7b9d-498a-b371-eda23d8c54f8` |
| 2 | B_relocated_executable | `4585e6ec-cf5b-44db-b097-faa3de9781ce` |
| 3 | C_compatible_host_drift | `03387d36-f745-4057-809b-35a8e187ce18` |
| 4 | D_incompatible_host_drift | `9ce5bbb3-6ab9-45c0-8862-4ef62451b2e2` |
| 5 | D_incompatible_host_drift | `f9da422a-e217-403d-8ee3-05019ee2cd20` |
| 6 | E_prefix_drift_windows | `54a2a22d-8829-4009-90da-777abbef9406` |
| 7 | E_prefix_drift_component | `16b52143-02be-4432-9d9f-5e1f1ada9d30` |
| 8 | F_clean_prefix_reconstruction | `3a7be2bd-5c22-452b-841f-e52d45356235` |
| 9 | G_known_compatibility_failure | `c9b1b0c1-8e64-4910-bf68-6aae71cdeaba` — **exploratory_only** |
| 10 | H_unrelated_runtime_failure | `f696b987-16a2-49cc-9b89-e46446ced9d2` |
| 11 | I_trust_state_imported | `81299847-6c92-463d-95c7-b11bffec84d2` |
| 12 | I_trust_state_invalidated | `50fd478d-f18a-4fc3-802a-7ae2f9b2e191` |
| 13 | J_multiple_candidate_ranking | `9dc70e4c-0a6b-46ac-990f-567fcb3672e3` |

### Gate results (scoped)

Per `data/validation/campaigns/pilot-005-package.md`:

| Gate | Result | Notes |
|------|--------|-------|
| min_comparisons | 9 / 50 required | **Failed** — volume shortfall |
| min_drift_scenarios | 2 / 10 required | **Failed** |
| min_rejection_scenarios | 4 / 10 required | **Failed** |
| min_program_kinds | 3 / 3 | Passed |
| eligibility_precision | 100% (9/9) | Passed |
| false_eligibility_rate | 0% | Passed |
| drift_false_positive_rate | 0% (6 drift checks) | Passed |
| rank_agreement | 8 / 8 | Passed |
| no_duplicate_profile_defects | 8 / 9 | **Failed** |

**Classification:** All safety *quality* metrics passed on scoped evidence, but **volume thresholds** were not met. Active reuse remains disabled. Pilot-001/002/003 evidence explicitly excluded via `gate_exclusions` in the evidence quality review.

---

## 8. Pilot-005 Corrective Engineering

**Status:** `PREPARED — NOT APPROVED FOR EXECUTION`  
**Package:** `data/validation/campaigns/pilot-005-package.md`  
**Tests:** `tests/test_pilot005_corrective.py` (17 tests)

Pilot-004 completion exposed infrastructure gaps, not fundamental shadow-design flaws. Pilot-005 prepares fixes without authorizing execution or reuse.

### Deliverables

| Area | Fix | Module |
|------|-----|--------|
| Campaign-scoped metrics | Gates filter by campaign ID; historical pollution removed | `profile_shadow_validation_scope.py`, `campaign_evidence.py` |
| Evidence-quality scoping | Immutable review artifact; exploratory runs excluded | `pilot-004-evidence-quality-review.json` |
| Authoritative manifest capture | Prefix state captured at verification time | `alma_bridge/compatibility/profile_manifest_capture.py` (`manifest_capture_v2`) |
| Ranking safety | Recency-only winners flagged `active_reuse_eligible=false` | `pilot-005-ranking-safety.md` |
| Duplicate-profile metric | Corrected: duplicate only when promoted ≠ predicted | `profile_shadow_comparison.py` |
| API-compatible known failure | Run G replacement without orchestrator bypass | `scripts/validation/pilot005_known_failure_precondition.py` |
| Evidence persistence | Atomic write + DB recovery path | `campaign_evidence.py` |

**Continuity policy:** `data/validation/campaigns/pilot-005-continuity-policy.md`

**Proposed additional runs:** ~48-run matrix to close volume gaps (41 comparisons, 8 drift, 6 rejection scenarios). **Not yet executed.**

---

## 9. Code::Blocks Breakthrough

**Application:** Code::Blocks 25.03 (32-bit)  
**Framework:** wxWidgets 3.2.7  
**Install path:** `~/.local/share/alma-bridge/prefixes/bc32ec33-b93/drive_c/Program Files (x86)/CodeBlocks/codeblocks.exe`  
**Fixture stderr:** `tests/fixtures/codeblocks_startup_stderr.txt`

This is Alma Bridge’s first verified **real-world IDE launch** through the full closed loop: classify → framework/runtime routing → launch → observe → verify usability → stop on success → preserve evidence.

### Problems discovered and fixed

| Defect | Symptom | Fix |
|--------|---------|-----|
| False `missing_visual_c_runtime` | Benign “Microsoft Visual C++” **compiler inventory** in startup stderr triggered runtime-missing signature | Tightened signature detection in `alma_bridge/execution/errors.py` |
| Electron handoff misrouting | wxWidgets GUI app routed through `electron_handoff` verifier instead of `wine_gui_handoff` | Framework-aware routing via `framework_detection.py`; `pe_windows_gui` → `wine_gui` phase |
| Stop-on-success gap | Install verified (attempt 3) but launcher loop continued without reaching `SUCCEEDED` | Orchestrator stop-on-success invariants; `_run_launcher_handoff` respects program kind |
| Single-instance relaunch | Second launch while IDE running failed all 5 attempts | Added `single_instance_detected` non-retryable signature + live-process guard in `wine_gui_handoff.py` |

### Session evidence

| Session | Role | Outcome |
|---------|------|---------|
| `bc32ec33-b936-4857-8834-d73349e46876` | Pre-fix install + launcher loop | Install attempt **3 passed** verification (`confidence: 0.925`); launcher attempts failed via `electron_handoff` / false `missing_visual_c_runtime`; session never reached `SUCCEEDED` |
| `4ecb0e85-af0c-4143-8b29-668cfccad37a` | Post-fix launch | **1 attempt**, phase `wine_gui`, verification **passed** (`wine_gui_handoff`, `process_survives`); session `SUCCEEDED` |
| `25ff2d44-d010-4df6-953c-c8cf70705776` | Single-instance guard validation | **5 attempts** failed before fix; after `single_instance_detected` guard, relaunch while IDE live is correctly classified |

### Regression tests

| File | Tests | Coverage |
|------|-------|----------|
| `tests/test_wxwidgets_framework.py` | 16 | Framework detection, false VC++ signal, single-instance guard, wxWidgets handoff |
| `tests/test_stop_on_success_orchestration.py` | 8 | Stop after verified success; no post-success retry loops |
| Focused suite (combined with Pilot-005 corrective) | 41 collected | All passed at time of Code::Blocks fix verification |

### Significance

Code::Blocks demonstrates the **ADR-001 closed loop** working on a non-trivial application:

1. **Classify** — `pe_windows_gui` + wxWidgets framework detected from bundled DLLs
2. **Route** — `wine_gui` phase with process-survival verification (not Electron handoff)
3. **Launch** — GUI detaches; target PID observed through survival window
4. **Verify** — `VerificationEngine` returns structured pass; only then `SUCCEEDED`
5. **Stop** — no further attempts after verified success
6. **Preserve** — session, attempts, and verification JSON persisted in `outcomes.db`

This is **execution-path proof**, distinct from CompatibilityProfile shadow promotion (which remains disabled).

---

## 10. Current State — PROVEN vs STILL UNDER VALIDATION

### PROVEN (with evidence)

| Capability | Evidence |
|------------|----------|
| Observe-only shadow predictions | Pilot-004 runs 1–8, 10–13; architecture review |
| Deterministic eligibility rejection | Host mismatch, trust exclusion, invalidation — Pilot-004 runs 4–5, 11–12 |
| Drift detection (windows, component) | Pilot-004 runs 6–7 |
| Deterministic multi-candidate ranking | Pilot-004 run 13 (session `9dc70e4c-…`) |
| Wine GUI verification contract | `pe_windows_gui` + `process_survives` — Pilot-002/003 prep, Code::Blocks |
| Framework-aware wxWidgets launch | Session `4ecb0e85-…`; tests in `test_wxwidgets_framework.py` |
| Stop-on-success orchestration | Session `4ecb0e85-…`; `test_stop_on_success_orchestration.py` |
| Authoritative verification boundary | ADR-001; Code::Blocks `SUCCEEDED` only after `VerificationEngine` pass |
| Lifecycle runaway prevention | Commit `9d2a2ac`; AutoCompatibilityBudget |
| Campaign prefix safety | Commit `9d2a2ac`; campaign_guard |

### STILL UNDER VALIDATION (not production-ready)

| Capability | Status | Blocker |
|------------|--------|---------|
| **Active CompatibilityProfile reuse** | **DISABLED** | Promotion volume gates not met; ranking safety advisory only |
| Shadow promotion to production | `COMPLETED_NOT_PROMOTION_READY` | Need ≥50 comparisons, ≥10 drift/rejection scenarios (Pilot-005 planned) |
| Manifest capture on legacy profiles | Partial | Pre-`manifest_capture_v2` profiles lack component data |
| Ascension nested launcher | Research blocked | Token/IPC attestation under Wine |
| Full promotion gate pass | Not achieved | Scoped Pilot-004: 9/50 comparisons |
| Pilot-005 execution | Not approved | Package prepared; awaiting explicit approval |
| Ranking formula calibration | Under review | Recency-only tiebreaks flagged but selection still follows raw score |

**Do not claim active profile reuse is production-ready.** Shadow mode continues to observe and compare without influencing execution.

---

## Milestone Timeline

| Milestone | Problem discovered | Correction | Result | Current status |
|-----------|-------------------|------------|--------|----------------|
| **Phase 2 shadow mode** | No structured way to evaluate reuse safety before enabling it | Observe-only predictions, deterministic eligibility/ranking, drift + comparison pipeline | Shadow subsystem integrated into orchestrator; reuse flag stays false | **Active** — foundation in place |
| **Validation infrastructure** | Ad-hoc testing risked polluting production data | Scenario manifests A–J, runbook, labels, gates, sanitized exports | Repeatable campaign workflow | **Active** — operational |
| **Pilot-001** | 622-attempt runaway loop; primary prefix mutated | Operator-terminated session `25238bf2-…` | Closed `exploratory_non_promotable` | **Closed** — excluded from gates |
| **Corrective engineering** | Unbounded auto-compat retries; illegal lifecycle transitions | Commit `9d2a2ac`: AutoCompatibilityBudget, guards, terminal observation | 527 tests passed; safe to resume campaigns | **Complete** |
| **Ascension investigation** | Sidecar token attestation impossible with decoy launcher | Moved to research; no false success claim | `ASCENSION_NESTED_SIDECAR_TOKEN_ATTESTATION_BLOCKED_UNDER_WINE` | **Research** — not a blocker for other apps |
| **Pilot-002** | Scenario ID manifest mismatch at Run 6 | Campaign aborted; freeze preserved | 6 runs exploratory; `exclude_from_gate_calculations` | **Closed** — non-promotable |
| **Pilot-003** | Invalid label type; drift/failure scenarios not induced | Corrective design fed into Pilot-004 | 11 runs; aborted `INVALID_LABEL_TYPE` | **Closed** — non-promotable |
| **Pilot-004** | Prior campaigns invalid; needed clean 13-scenario pass | Freeze `6261d47`; pre-plan overlay, typed labels, manifest fixes | 12 promotion-eligible runs; safety metrics pass; volume gates fail | **Complete** — `NOT_PROMOTION_READY` |
| **Pilot-005 prep** | Global gate pollution; incomplete manifest capture; ranking safety gaps | Corrective package + 17 tests; manifest_capture_v2 | Prepared, not executed | **Pending approval** |
| **Code::Blocks launch** | False VC++ signal; Electron misrouting; no stop-on-success; single-instance relaunch | Framework detection, wine_gui handoff, orchestration fixes | Verified IDE launch session `4ecb0e85-…` | **Proven** — real-world closed loop |

---

## Where Alma Bridge Is Now

Alma Bridge can **install and launch a real Windows IDE (Code::Blocks 25.03) on Linux through Wine**, verify that the application is genuinely running, and **stop trying once it succeeds**. That end-to-end path — from “run this `.exe`” to “the app is usable” — is working and tested.

In parallel, Alma has built a careful **learning system** that records what worked and predicts whether saved configurations would help future runs — but it deliberately **does not act on those predictions yet**. Four validation campaigns (Pilot-001 through Pilot-004) produced the evidence and corrections needed to trust the safety properties of that learning system. Pilot-004 proved the shadow observer correctly handles host mismatches, configuration drift, untrusted profiles, and ranking — but not enough runs exist yet to unlock automatic reuse.

**Ascension** (the original game-launcher target) remains blocked by a Wine-specific security handshake that requires further research — this does not block other applications.

**Bottom line:** Alma Bridge is a working application launcher with rigorous verification. Its compatibility-learning feature is built, shadow-tested, and conservatively gated — ready for more validation (Pilot-005), not ready for automatic profile reuse in production.

---

## Key artifact index

| Artifact | Path |
|----------|------|
| Shadow validation runbook | `docs/operations/shadow-validation-runbook.md` |
| Architecture review | `docs/reviews/compatibility-profile-architecture-review.md` |
| ADR-001 lifecycle | `docs/adr/ADR-001-authoritative-bridge-lifecycle.md` |
| Pilot-001 manifest | `data/validation/campaigns/shadow-validation-pilot-001.json` |
| Pilot-002 closure | `data/validation/campaigns/shadow-validation-pilot-002-closure.json` |
| Pilot-003 closure | `data/validation/campaigns/shadow-validation-pilot-003-closure.json` |
| Pilot-004 evidence review | `data/validation/campaigns/pilot-004-evidence-quality-review.json` |
| Pilot-005 package | `data/validation/campaigns/pilot-005-package.md` |
| Ascension research | `data/validation/research/ascension-nested-sidecar-token-attestation.md` |
| Corrective commit | `9d2a2ac` |
| Pilot-004 freeze commit | `6261d47` |
| wxWidgets tests | `tests/test_wxwidgets_framework.py` (16 tests) |
| Stop-on-success tests | `tests/test_stop_on_success_orchestration.py` (8 tests) |
| Pilot-005 corrective tests | `tests/test_pilot005_corrective.py` (17 tests) |
| Platform direction (architecture) | [docs/architecture/alma-bridge-platform-direction.md](../architecture/alma-bridge-platform-direction.md) |
