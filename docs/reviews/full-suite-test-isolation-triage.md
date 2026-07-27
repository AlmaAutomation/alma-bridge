# Full-Suite Test Isolation Triage

**Date:** 2026-07-27  
**Baseline commit:** `f9948bb`  
**Outcome:** All 9 stable full-suite failures resolved via test-only isolation fixes (678 passed / 2 skipped × 3 consecutive runs)

---

## 1. Environment

| Item | Value |
|------|-------|
| Command | `PYTHONPATH=<repo-root> .venv/bin/pytest -q` |
| Python | 3.12.3 |
| pytest | 9.0.3 |
| Collected tests | 680 (678 passed + 2 skipped after fix) |
| Collection order | `/tmp/pytest-order.txt` (686 lines, captured via `pytest --collect-only -q`) |

---

## 2. Summary

All nine failures shared a **single root cause**: `test_import_intelligence_routes_does_not_load_orchestrator` popped `alma_bridge.learning.orchestrator` from `sys.modules` without restoring it. That orphaned the orchestrator module object imported at collection time (by test modules and `conftest`) while subsequent `monkeypatch.setattr("alma_bridge.learning.orchestrator.*", …)` calls bound to a **new** module in `sys.modules`. Patches never reached code executed by `BridgeOrchestrator` instances or the global `api.routes.orchestrator` singleton.

**Fixes applied (test-only):**

1. **`tests/intelligence/test_architecture_boundaries.py`** — save/restore `sys.modules` entries in `finally` after the import-boundary assertion.
2. **`tests/conftest.py`** — autouse `_stabilize_orchestrator_bindings` fixture: pin `sys.modules["alma_bridge.learning.orchestrator"]` to the collection-time module and refresh `api.routes.orchestrator = BridgeOrchestrator()` after each test.
3. **`tests/test_suite_isolation.py`** — two regression tests proving module identity survives the import-boundary pattern and that `monkeypatch` reaches the canonical module.

No production code changes.

---

## 3. Per-victim triage

| # | Victim | Minimal polluter | Leaked state | Corrective action |
|---|--------|------------------|--------------|-------------------|
| 1 | `test_orchestrator_applies_preferred_remediation_first` | `test_import_intelligence_routes_does_not_load_orchestrator` (index 6) | Orphaned orchestrator module; `monkeypatch` on `_next_remediation` / `execute_attempt` missed `/bridge/run` path via stale `api.routes.orchestrator` | Import-boundary teardown + autouse stabilize fixture |
| 2 | `test_wxwidgets_handoff_excludes_electron_env` | Same | `execute_attempt` mock not applied; real Wine execution ran | Same |
| 3 | `test_successful_first_gui_attempt_stops_remaining_strategy_iteration` | Same | `execute_attempt` mock not applied; stop-on-success logic never exercised with fakes | Same |
| 4 | `test_successful_second_attempt_stops_third_attempt` | Same | Same | Same |
| 5 | `test_failed_verification_still_allows_next_attempt` | Same | Same | Same |
| 6 | `test_process_launch_without_verification_does_not_stop_retries` | Same | Same | Same |
| 7 | `test_verified_codeblock_handoff_stops_later_attempts` | Same | Same | Same |
| 8 | `test_verification_persistence_failure_cannot_produce_succeeded` | Same | `_persist_attempt` raise-patch missed; real persist succeeded → `result.success is True` | Same |
| 9 | `test_native_console_pe_still_uses_exit_code_contract` | Same | Real execution / unpatchable `_persist_attempt`; `retrieve_persisted_verification` returned `None` | Same |

### Binary-search evidence (victim #1)

```
MINIMAL_POLLUTER_INDEX 6
POLLUTER tests/intelligence/test_architecture_boundaries.py::TestIntelligenceArchitectureBoundaries::test_import_intelligence_routes_does_not_load_orchestrator
VICTIM   tests/test_orchestrator_retries.py::test_orchestrator_applies_preferred_remediation_first
```

Reproduction before fix:

```bash
pytest -q \
  tests/intelligence/test_architecture_boundaries.py::TestIntelligenceArchitectureBoundaries::test_import_intelligence_routes_does_not_load_orchestrator \
  tests/test_orchestrator_retries.py::test_orchestrator_applies_preferred_remediation_first
# → FAILED assert body["success"] is True  (got False)
```

### Mechanism (verified in REPL)

After the polluter runs:

- `"alma_bridge.learning.orchestrator" not in sys.modules`
- Test modules still hold `BridgeOrchestrator` from the **old** module object (collection-time import)
- `monkeypatch.setattr("alma_bridge.learning.orchestrator.execute_attempt", fake)` patches the **new** module loaded into `sys.modules`
- `BridgeOrchestrator().run()` resolves `execute_attempt` from the **old** module namespace → real execution

---

## 4. Shared state inspected

| Suspect | Finding |
|---------|---------|
| Global `orchestrator = BridgeOrchestrator()` in `alma_bridge/api/routes.py:149` | Stale instance after module swap; refreshed by autouse fixture |
| `test_orchestrator_retries.py` patches on `orch` module attrs | Harmless when module identity stable; failed when module orphaned |
| `test_profile_shadow.py` `_persist_attempt` no-op patches | Not a polluter; `monkeypatch` teardown works when module identity stable |
| `apply_ml_wine_fix` Mock leak (`test_ml_wine_fix.py`) | Already guarded by `test_apply_ml_wine_fix_is_real_callable_after_collection`; not implicated |
| `conftest.py` autouse DB/path isolation | Unrelated; failures persisted with isolated tmp paths |
| Strategy registries / lru_cache / env vars | Not implicated |

---

## 5. Isolation proof

### Regression tests added

```python
# tests/test_suite_isolation.py
test_orchestrator_module_survives_intelligence_import_boundary
test_monkeypatch_reaches_orchestrator_after_import_boundary
```

### Targeted validation

```bash
# All 9 victims + polluter + isolation regressions
pytest -q \
  tests/intelligence/test_architecture_boundaries.py::TestIntelligenceArchitectureBoundaries::test_import_intelligence_routes_does_not_load_orchestrator \
  tests/test_orchestrator_retries.py::test_orchestrator_applies_preferred_remediation_first \
  tests/test_stop_on_success_orchestration.py \
  tests/test_orchestrator_wxwidgets_routing.py::test_wxwidgets_handoff_excludes_electron_env \
  tests/test_verification_authority.py::TestOrchestratorVerificationAuthority::test_verification_persistence_failure_cannot_produce_succeeded \
  tests/test_wine_gui_contract.py::test_native_console_pe_still_uses_exit_code_contract \
  tests/test_suite_isolation.py
# → 18 passed
```

### Final gate (three consecutive full-suite runs)

| Run | Passed | Failed | Skipped | Duration |
|-----|--------|--------|---------|----------|
| 1 | 678 | 0 | 2 | 405.89s |
| 2 | 678 | 0 | 2 | 446.54s |
| 3 | 678 | 0 | 2 | 484.48s |

---

## 6. Files changed

| File | Change |
|------|--------|
| `tests/intelligence/test_architecture_boundaries.py` | Restore `sys.modules` in `finally` after import-boundary test |
| `tests/conftest.py` | Autouse `_stabilize_orchestrator_bindings` fixture |
| `tests/test_suite_isolation.py` | Two regression tests for module identity + monkeypatch reachability |
| `scripts/find_polluters.py` | Binary-search helper for future isolation work (optional tooling) |

---

## 7. Prior suspects ruled out

- **Changing test order** — not used; root cause is deterministic at collection index 6.
- **Sleeps / weakened assertions / xfail** — not used.
- **Production orchestrator / verification / stop-on-success logic** — no changes; failures were patch reachability, not behavior regressions.
