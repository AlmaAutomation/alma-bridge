# Pilot-002 Approval Package — Ascension Baseline Investigation

**Date:** 2026-07-13  
**Status:** Pilot-002 **NOT APPROVED** — verified baseline not established  
**Corrective engineering commit:** `9d2a2ac` (`fix: bound auto-compatibility and harden validation lifecycle`)

---

## 1. Corrective Engineering & Working Tree

| Item | Value |
|------|-------|
| Corrective engineering SHA | `9d2a2ac` |
| Full suite at corrective commit | 527 passed |
| Clean tree at `9d2a2ac` | Yes |
| Pending freeze commit (uncommitted) | Investigation script + pilot-001 Run 4 manifest closure |

**Proposed freeze commit message:**

```
chore: ascension baseline investigation harness and pilot-001 run4 closure
```

Files: `scripts/validation/ascension_baseline_investigate.py`, `data/validation/campaigns/shadow-validation-pilot-001.json`

Secret scan on pending files: no credentials, tokens, or key material detected.

---

## 2. Pilot-001 Run 4 Closure

| Field | Value |
|-------|-------|
| Event | `OPERATOR_TERMINATED_RUNAWAY_SESSION` |
| Session | `25238bf2-8ea4-4dc6-9d07-01f8255ef24d` |
| Bridge PID | `1087988` (SIGTERM → SIGKILL) |
| Attempts at termination | 622 (`invalid_launch_args` loop) |
| DB modified | No |
| Evidence | `data/validation/evidence/pilot-001/run04/OPERATOR_TERMINATED_RUNAWAY_SESSION.json` |
| Promotion eligible | No |

---

## 3. Nested vs Flat Launcher Comparison

| Dimension | Nested (campaign canonical) | Flat (historical) |
|-----------|---------------------------|-------------------|
| Path layout | `…/Ascension Launcher/Ascension Launcher/Ascension Launcher.exe` | `…/Ascension Launcher/Ascension Launcher.exe` |
| Executable SHA-256 | `6b76d81a8655e6d84ddc66385b8865390a4b8ffde3b5b433a88159f2978e73f6` | `cfed75630a91f1d03958c42bffad500e1e97f3cb2becc2bcb5c6a0b81cb8ca99` |
| Size | 226832384 | 226832384 |
| PE linker date | Apr 28 2026 | Apr 28 2026 |
| Imported DLLs | Same set | Same set |
| `app.asar` SHA-256 | `c6cd21f4…` (15277305 B) | `d4e8b1a2…` (15277307 B) |
| Sidecar/wrapper hashes | Differ | Differ |

**Classification: A — different application build** (same size/name, not mergeable identities).

---

## 4. Control Experiment Matrix (v2 methodology)

Methodology revision `v2_prefix_local_launcher_no_cli_flags`: launcher resolved from disposable clone; no Chromium CLI flags on direct Wine controls.

| Control | Setup | Failure signature | Sidecar invoke | Sidecar output | Notes |
|---------|-------|-------------------|----------------|----------------|-------|
| C1 | Flat + historical clone | `dotnet_missing` | 0 | 0 | Flat build on historical prefix |
| C2 | Flat + fresh prefix | `dotnet_missing` | 0 | 0 | Prefix state insufficient alone |
| C3 | Nested + snapshot clone + Alma prep | `dotnet_missing` | 25505 B | 0 | Sidecar invoked, silent |
| C4 | Nested + fresh prefix + Alma prep | `dotnet_missing` | 0 | 0 | No install tree in fresh prefix |
| C5 | Nested + snapshot, no Alma prep | `dotnet_missing` | 25505 B | 0 | Prep not sole differentiator |
| C6 | Nested + snapshot, Alma Wine env | `unknown_error` | 25505 B | 0 | Harness env contamination noted |
| C7 | Nested + snapshot via BridgeOrchestrator | **NOT RUN** | — | — | Operator action required |

Evidence: `data/validation/evidence/ascension-baseline/C*.json`, `control_matrix.json`

**v1 matrix invalidation:** Initial controls used `--disable-gpu --no-sandbox` CLI flags and primary-prefix launcher paths. Nested launcher rejects those flags (`bad option`). v1 `invalid_launch_args` results are harness artifacts, not application conclusions.

---

## 5. First Divergence Timeline (nested + snapshot path)

```
prefix cloned (source snapshot hash 8e0c5f18…)
  → launcher invoked from clone (sha 6b76d81a…)
  → Electron bootstrap starts
  → sidecar guard invokes AscensionClientServices (alma-cs-invoke.log = 25505 B)
  → sidecar produces zero output (alma-cs-output.log = 0 B)
  → 45s direct-Wine observation ends with dotnet_missing / unknown_error
  → VerificationEngine never reached (direct Wine controls)
```

**Earliest substantive divergence:** sidecar invocation with silent output (consistent with pilot-001 Run 1 `sidecar_silent_crash`).

**Classification:** Wine/runtime sidecar failure on nested build — not verification false negative (Bridge not exercised in C1–C6).

Alma preparation (C3 vs C5): same sidecar signature — **not** the first divergence.

---

## 6. Canonical Ascension Target Rule

| Rule | Definition |
|------|------------|
| Canonical executable selection | `ascension_main_launcher_path(wine_prefix)` — largest non-`alma-guard` `Ascension Launcher.exe` under `drive_c/Program Files/Ascension Launcher/` |
| Canonical program identity | SHA-256 of resolved executable bytes |
| Nested vs flat | **Separate program identities** (`6b76d81a…` ≠ `cfed7563…`) |
| `/bridge/run` target | Resolved canonical launcher path **inside** the disposable `wine_prefix` |
| Installer-discovered launchers | Normalize via `ascension_main_launcher_path`; never merge by filename/size |
| Launcher updates | New executable hash → new program identity; invalidates prior profiles |

**Campaign canonical build:** nested `6b76d81a8655e6d84ddc66385b8865390a4b8ffde3b5b433a88159f2978e73f6` on source snapshot class `8e0c5f18…`.

---

## 7. Root Cause & Correction

**Proven root cause (investigation stage):** Not sufficient for code change yet. C7 (BridgeOrchestrator with remediation chain, winetricks bootstrap, verification) is required before attributing failure to Bridge vs Wine sidecar.

**No corrective code implemented** — per instruction, no speculative Ascension remediation chains.

**No regression test added** — baseline not reproduced.

---

## 8. Verified Baseline Acceptance

| Criterion | Run A | Run B |
|-----------|-------|-------|
| Fresh disposable clone | — | — |
| Canonical nested identity | — | — |
| BridgeOrchestrator + VerificationEngine | — | — |
| SUCCEEDED via VERIFYING | — | — |
| ProfileCandidate + locally_verified profile | — | — |
| ShadowActualOutcome | — | — |

**Status: NOT ESTABLISHED**

---

## 9. Prefix Integrity Hashes (unchanged)

| Prefix | Aggregate hash (sample) |
|--------|-------------------------|
| Primary (`803984cf-660`) | `46c9e977d4b263f89147e4eeadfd04b67045b81cd0cc88fa380196517dd6fa7c` |
| Source snapshot | `8e0c5f18d63b985a19bc87ba9d0ac294a5e2b031e63a821cc4f08b7fea75bb1f` |
| Historical flat (`0aaabfa5-6c9`) | `1fd185e762e768d2480f1924ba2e8a3a14ca84959b1bc2ebf76d0289f7597aee` |

Primary and source snapshot were not mutated during investigation.

---

## 10. AutoCompatibilityBudget

Counters from corrective engineering (`9d2a2ac`): session-scoped limits active. Run 4 runaway (622 attempts, pre-corrective binary) excluded from promotion metrics.

---

## 11. Operator Actions Before Pilot-002 Approval

1. Commit pending investigation harness + Run 4 manifest closure.
2. Run C7 on disposable clone:

```bash
cd /home/joshua/Desktop/Alma/alma-bridge
python3 scripts/validation/ascension_baseline_investigate.py --bridge-only
```

3. If C7 fails with `sidecar_silent_crash`, diagnose sidecar under Wine before any product-code change.
4. Execute verified baseline Runs A & B only after C7 characterizes Bridge path.
5. Re-run full suite before Pilot-002 freeze.

**Pilot-002 remains `planned` — do not execute until explicitly approved.**
