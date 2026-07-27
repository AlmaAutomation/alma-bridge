# Compatibility Intelligence Phase 1 — Regression Triage

**Date:** 2026-07-27  
**Branch state:** Uncommitted working tree on detached HEAD `6261d47` (intelligence package + integration not yet committed)  
**Triage outcome:** **Outcome B** — no intelligence-attributable regressions; 3 non-intelligence failures remain outside sandbox (644 passed / 3 failed)

---

## 1. Test command and environment

| Item | Value |
|------|-------|
| Command | `PYTHONPATH=<repo-root> .venv/bin/pytest -q` |
| Python | 3.12.3 |
| pytest | 9.0.3 |
| venv | `/home/joshua/Desktop/Alma/alma-bridge/.venv` (editable `alma-bridge` 0.1.0) |
| OS | Linux (Ubuntu 24.04, kernel 7.0.0-28-generic) |
| CI equivalent | `pip install -e ".[dev]" && pytest -q` (`.github/workflows/ci.yml`) |

**Sandbox note:** Cursor agent sandbox runs exhibited 13 additional failures (16 total) due to `[Errno 13] Permission denied` writing `~/.local/share/alma-bridge/prefixes/` (directory owned by root). Re-running the same tests **outside sandbox** with full filesystem access: those 13 tests **pass**.

---

## 2. Baseline comparison

| | Baseline | Current (intelligence branch) |
|---|----------|-------------------------------|
| **Commit** | `6261d47` — *Freeze Pilot-004 validation campaign after setup and pre-execution proofs.* | Same base + uncommitted intelligence/integration changes |
| **Worktree** | `/tmp/alma-bridge-baseline` (git worktree, detached) | `/home/joshua/Desktop/Alma/alma-bridge` |
| **Total collected** | 586 | 647 (+61 intelligence/new tests) |
| **Passed (unsandboxed)** | 575 | 644 |
| **Failed (unsandboxed)** | 11 | 3 |
| **Skipped** | 0 | 2 |

### Baseline-only failures (not in current 16)

All 11 baseline failures are in `tests/test_electron_handoff.py` — missing fixture files in the baseline worktree (`tests/fixtures/sidecar/*.log`). Current tree includes handoff fixes (`alma_bridge/execution/wine_gui_handoff.py`) and passes all electron handoff tests.

### New failures vs baseline (unsandboxed)

| Test | Baseline | Current |
|------|----------|---------|
| `test_installer_not_verified_remediation_chain_order` | PASS | FAIL |
| `test_orchestrator_retries_multiple_strategies` | PASS | FAIL |
| `test_orchestrator_reranks_remaining_strategies` | PASS | FAIL |

The 13 tests listed in the task brief that fail in sandbox **pass on both baseline and current** when run unsandboxed.

---

## 3. Grouped root causes

### RC-A — Sandbox prefix write denial (13 tests)

**Symptom:** `Bridge session internal error: [Errno 13] Permission denied: '/home/joshua/.local/share/alma-bridge/prefixes/<session-id>'`  
**Stack frame:** `alma_bridge/learning/orchestrator.py` → `fresh_prefix_path()` during native/Wine session setup  
**Subsystem:** Execution / prefix provisioning  
**Intelligence touch:** None (indirect only via shared `routes.py` orchestrator, unchanged dependency path)

Orchestrator creates session-scoped Wine prefixes under the configured data directory before attempt execution. Sandbox blocks writes to the root-owned prefixes tree.

### RC-B — Non-retryable signature early exit (2 tests)

**Symptom:** `assert len(attempts) >= 2` fails with exactly 1 attempt; `error_signature: permission_denied`  
**Stack frame:** `alma_bridge/learning/orchestrator.py` (~line 769) — `NON_RETRYABLE_SIGNATURES` clears remaining plans  
**Subsystem:** Orchestrator retry loop  
**Intelligence touch:** None  
**Introduced by:** `alma_bridge/execution/errors.py` — `NON_RETRYABLE_SIGNATURES` frozenset (includes `permission_denied`)

### RC-C — Learned remediation ordering (1 test)

**Symptom:** `installer_fresh_prefix_silent` sorts ahead of `installer_bootstrap_win10_vcrun_ncrc`  
**Stack frame:** `alma_bridge/learning/remediation.py:768` — `remediation_scores()` sort key  
**Subsystem:** Remediation learning (shared outcomes DB)  
**Intelligence touch:** None  
**Note:** `remediation.py` is unchanged vs baseline; order differs because `remediation_scores()` reads accumulated rates from the shared developer DB.

---

## 4. Classification of all 16 failures

| # | Test | Exception / assertion | First app frame | Subsystem | Intelligence import? | Classification |
|---|------|----------------------|-----------------|-----------|---------------------|----------------|
| 1 | `test_architecture_invariants.py::TestBehavioralInvariants::test_only_verification_gateway_may_reach_succeeded` | `assert len(succeeded) == 1` → 0 | `orchestrator.py` / session lifecycle | Verification gateway | Indirect (via routes orchestrator) | **ENVIRONMENT_FAILURE** |
| 2 | `test_architecture_invariants.py::TestBehavioralInvariants::test_succeeded_session_has_verification_json` | `assert winning is not None` | `orchestrator.py` | Verification gateway | Indirect | **ENVIRONMENT_FAILURE** |
| 3 | `test_auto_compat_lifecycle.py::test_lifecycle_exception_records_shadow_actual` | `assert count >= 1` → 0 shadow rows | `orchestrator.py` / shadow capture | Compatibility shadow | Indirect | **ENVIRONMENT_FAILURE** |
| 4 | `test_bridge.py::test_prior_success_endpoint` | `assert body["found"] is True` → False | `routes.py` → `orchestrator.run` | Bridge API | Indirect (routes include intelligence router) | **ENVIRONMENT_FAILURE** |
| 5 | `test_bridge.py::test_bridge_sessions_include_attempt_metadata` | `assert session["attempt_count"] >= 1` → 0 | `routes.py` | Bridge API | Indirect | **ENVIRONMENT_FAILURE** |
| 6 | `test_bridge.py::test_bridge_run_native_script` | `assert body["success"] is True` → False | `orchestrator.py` / `fresh_prefix_path` | Bridge execution | Indirect | **ENVIRONMENT_FAILURE** |
| 7 | `test_installer_verify.py::test_installer_not_verified_remediation_chain_order` | First id `installer_fresh_prefix_silent` ≠ expected bootstrap | `remediation.py:768` | Remediation learning | No | **TEST_ISOLATION_FAILURE** |
| 8 | `test_orchestrator_retries.py::test_orchestrator_retries_multiple_strategies` | `assert len(attempts) >= 2` → 1 | `orchestrator.py` NON_RETRYABLE break | Orchestrator retry | No | **UNRELATED_NEW_DEFECT** |
| 9 | `test_orchestrator_retries.py::test_orchestrator_reranks_remaining_strategies` | `assert rerank_calls` → [] | `orchestrator.py` | Orchestrator rerank | No | **UNRELATED_NEW_DEFECT** |
| 10 | `test_terminal_observation.py::test_failure_records_single_shadow_actual[True]` | Shadow actual count assertion | `orchestrator.py` | Shadow observation | Indirect | **ENVIRONMENT_FAILURE** |
| 11 | `test_terminal_observation.py::test_budget_exhaustion_records_shadow_actual` | Budget message not in summary (permission error instead) | `orchestrator.py` / `fresh_prefix_path` | Shadow + budget | Indirect | **ENVIRONMENT_FAILURE** |
| 12 | `test_terminal_observation.py::test_internal_exception_records_shadow_actual` | `_actual_count == 1` → 0 | `orchestrator.py` | Shadow observation | Indirect | **ENVIRONMENT_FAILURE** |
| 13 | `test_verification_authority.py::…::test_successful_attempt_has_persisted_verification_json` | `assert result.success is True` → False | `orchestrator.py` | Verification authority | No | **ENVIRONMENT_FAILURE** |
| 14 | `test_verification_authority.py::…::test_every_check_has_verifier_provenance` | `TypeError: 'NoneType' object is not subscriptable` (no winning attempt) | `orchestrator.py` | Verification authority | No | **ENVIRONMENT_FAILURE** |
| 15 | `test_verification_authority.py::…::test_succeeded_transition_origin_is_verifying` | `assert len(succeeded) == 1` → 0 | `orchestrator.py` | Verification authority | No | **ENVIRONMENT_FAILURE** |
| 16 | `test_wine_gui_contract.py::test_setup_preflight_retrieves_verification_via_get_session` | `assert verification is not None` | `orchestrator.py` | Wine GUI verification | No | **ENVIRONMENT_FAILURE** |

**Summary:** 0 × INTELLIGENCE_REGRESSION · 0 × PRE_EXISTING_FAILURE (unsandboxed) · 13 × ENVIRONMENT_FAILURE (sandbox-only) · 1 × TEST_ISOLATION_FAILURE · 2 × UNRELATED_NEW_DEFECT · 0 × UNKNOWN

---

## 5. Fixes made

| Fix | File | Rationale |
|-----|------|-----------|
| Remove `ensure_profile_tables()` from intelligence read path | `alma_bridge/intelligence/repository.py` | Repository adapter must not mutate schema on reads (ADR-002 boundary) |
| Return `None` on missing shadow-comparison table | `alma_bridge/intelligence/repository.py` | Read-only graceful degradation instead of `OperationalError` |
| Add import side-effect boundary tests | `tests/intelligence/test_architecture_boundaries.py` | Confirm intelligence package/routes don't init DB or load orchestrator |
| Add repository schema non-mutation test | `tests/intelligence/test_architecture_boundaries.py` | Regression guard for read-path DDL |
| Add `/bridge/run` dependency unchanged test | `tests/intelligence/test_architecture_boundaries.py` | Router wiring doesn't replace bridge entry points |

**Intentionally not fixed (per triage scope):**

- Orchestrator `NON_RETRYABLE_SIGNATURES` / stop-on-success changes — not intelligence-attributable
- Remediation learned-rate ordering — test isolation / shared DB, not intelligence
- Sandbox prefix permissions — environment, not code

---

## 6. Remaining failures

### Unsandboxed full suite (authoritative)

```
FAILED tests/test_installer_verify.py::test_installer_not_verified_remediation_chain_order
FAILED tests/test_orchestrator_retries.py::test_orchestrator_retries_multiple_strategies
FAILED tests/test_orchestrator_retries.py::test_orchestrator_reranks_remaining_strategies
3 failed, 644 passed, 2 skipped
```

### Intelligence suite

```
22 passed (tests/intelligence/)
```

---

## 7. Evidence for pre-existing / environment designations

### ENVIRONMENT_FAILURE (RC-A) — sandbox prefix denial

**Current (sandbox):**
```
summary: "Bridge session internal error: [Errno 13] Permission denied:
  '/home/joshua/.local/share/alma-bridge/prefixes/17f01557-709'"
attempts: []
success: false
```

**Baseline (sandbox):** Identical failure mode on `tests/test_bridge.py::test_bridge_run_native_script`.

**Both trees (unsandboxed):** Same test **PASSES** (verified 2026-07-27).

**Directory ownership:**
```
drwxrwxr-x 1085 root root ... ~/.local/share/alma-bridge/prefixes
```

### PRE_EXISTING / parity — 13 sandbox failures absent unsandboxed

Targeted re-run outside sandbox:
```bash
PYTHONPATH=. .venv/bin/pytest \
  tests/test_architecture_invariants.py \
  tests/test_auto_compat_lifecycle.py \
  tests/test_bridge.py \
  tests/test_terminal_observation.py \
  tests/test_verification_authority.py \
  tests/test_wine_gui_contract.py -q
# 62 passed
```

Same command on baseline worktree: equivalent pass set (minus intelligence-only tests).

### UNRELATED_NEW_DEFECT (RC-B) — orchestrator retries

Baseline passes; current fails with single attempt stopped by `permission_denied ∈ NON_RETRYABLE_SIGNATURES`.

```bash
# Baseline
cd /tmp/alma-bridge-baseline && PYTHONPATH=... pytest tests/test_orchestrator_retries.py -q
# 6 passed

# Current
cd alma-bridge && PYTHONPATH=. pytest tests/test_orchestrator_retries.py -q
# 2 failed
```

`git diff 6261d47 -- alma_bridge/execution/errors.py` shows `NON_RETRYABLE_SIGNATURES` addition; `orchestrator.py` consumes it. No intelligence files touched.

### TEST_ISOLATION_FAILURE (RC-C) — installer remediation order

`remediation.py` unchanged vs baseline. Order driven by live `remediation_scores()` from shared DB:

```python
# Baseline order (6261d47 code, shared venv)
['installer_bootstrap_win10_vcrun_ncrc', 'installer_bootstrap_full_ncrc', ...]

# Current order (same remediation.py, shared DB)
['installer_fresh_prefix_silent', 'installer_virtual_desktop_silent', ...]
```

Baseline full-suite run passed this test; failure is order-dependent on accumulated learning state.

### Intelligence boundary verification

```python
import alma_bridge.intelligence          # orchestrator NOT in sys.modules
import alma_bridge.api.intelligence_routes  # orchestrator NOT in sys.modules
# routes.py still: BridgeOrchestrator() + include_router(intelligence_router)
```

---

## Appendix — Targeted test commands run

### Pre-commit (Task A, 2026-07-27 sandbox)

```bash
pytest tests/intelligence -q                                    # 22 passed
pytest tests/test_architecture_invariants.py -q                 # 9 passed, 2 failed (sandbox prefix)
pytest tests/test_verification_authority.py -q                  # 14 passed, 3 failed (sandbox prefix)
pytest tests/test_bridge.py -q                                  # 8 passed, 3 failed (sandbox prefix)
```

Sandbox failures are RC-A (`fresh_prefix_path` under `~/.local/share/alma-bridge/prefixes/`); intelligence suite clean. Addressed in commit `test(config): redirect test data paths to temporary storage`.

### Full suite (unsandboxed, pre-fix)

```bash
pytest tests/intelligence -q                                    # 22 passed
pytest tests/test_architecture_invariants.py -q                 # pass (unsandboxed)
pytest tests/test_verification_authority.py -q                 # pass (unsandboxed)
pytest tests/test_bridge.py -q                                 # pass (unsandboxed)
pytest tests -q --maxfail=16                                   # 16 fail (sandbox only)
```
