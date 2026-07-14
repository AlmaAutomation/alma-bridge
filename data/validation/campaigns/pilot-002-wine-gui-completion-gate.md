# Pilot-002 Wine GUI Contract — Completion Gate

**Date:** 2026-07-13  
**Status:** Wine GUI execution/verification contract implemented; freeze package revised; **no freeze commit created** per operator instruction.  
**Baseline SHA (prep):** `0f91cae95f7efd6c816c5544a9bf417a285f3d6b`  
**Proposed freeze commit:** pending operator approval (working tree contains contract changes)

---

## 1. Preflight import defect fix

| Item | Resolution |
|------|------------|
| Defect | Setup script imported nonexistent `get_attempt_verification` from `outcomes.py` |
| Fix | `retrieve_persisted_verification()` uses existing `outcomes.get_session()` → `winning_attempt.verification` |
| Module | `alma_bridge/validation/setup_preflight.py` |
| CLI | `scripts/validation/pilot002_setup_preflight.py` |
| Test | `tests/test_wine_gui_contract.py::test_setup_preflight_retrieves_verification_via_get_session` |

---

## 2. PE classification rules

**Precedence (highest first):** installer → Electron launcher → `pe_windows_gui` → `pe_windows` (console) → native kinds.

| Executable | PE subsystem | program_kind | Execution phase | Required check |
|------------|--------------|--------------|-----------------|----------------|
| notepad.exe | GUI (2) | `pe_windows_gui` | `wine_gui` | `process_survives` |
| wordpad.exe | GUI (2) | `pe_windows_gui` | `wine_gui` | `process_survives` |
| write.exe | GUI (2) | `pe_windows_gui` | `wine_gui` | `process_survives` |
| PE console `.exe` | CUI (3) | `pe_windows` | `native` | `exit_code_zero` |
| Electron launcher | GUI (2) + markers | `pe_electron_launcher` | `launcher` | `process_survives` (electron_handoff) |
| Installer | — | `pe_installer` | `install` | installer checks |

**PE subsystem fix:** corrected PE32+ optional-header offset (subsystem at +68, not +76).

**Ordinary Wine GUI skip:** `pe_windows_gui` does not trigger VC++/NET bootstrap (`_artifact_needs_dotnet_bootstrap` returns false).

---

## 3. Execution contract changes

| Component | Change |
|-----------|--------|
| Orchestrator | `wine_gui_launch` path: GUI detach, bounded bootstrap timeout, baseline PID snapshot |
| Phase | `wine_gui` (distinct from Electron `launcher`) |
| Runner | Detach message: `[Alma] GUI detached` |
| BridgeRequest | Setup passes explicit `wine_prefix` (no fresh-prefix drift) |
| Config | `wine_gui_startup_timeout_sec`, `wine_gui_survival_sec`, `wine_gui_bootstrap_timeout_sec` |

**Flow:** launch → detach after bootstrap → observe target PID → survival window → verify → `SUCCEEDED` (no manual GUI closure).

---

## 4. Wine GUI verification policy

| Field | Value |
|-------|-------|
| Policy ID | `wine_gui_process_v1` |
| Policy version | `1.0.0` |
| Phase | `wine_gui` |
| Required checks | `process_survives` |
| Optional checks | `target_process_identity` |
| Verifier | `wine_gui_handoff` v1.1.0 |
| Contract | `WINE_GUI_HANDOFF_CONTRACT_VERSION = wine_gui_process_v1` |

Success requires target executable process identity — not wineserver/wine64 alone.

---

## 5. Process tracking

**Module:** `alma_bridge/execution/wine_process.py`

- `find_target_gui_processes()` / `wine_has_target_gui_process()`
- `observe_target_gui_process()` — startup + survival windows
- `TargetProcessMatch` / `TargetGuiObservation` evidence
- Wine infra exclusion (`wineserver`, `explorer.exe`, etc.)
- `terminate_owned_target_processes()` for campaign cleanup

**Handoff:** `alma_bridge/execution/wine_gui_handoff.py` → `evaluate_wine_gui_launch_result()`

---

## 6. Tests added

| Test file | Coverage |
|-----------|----------|
| `tests/test_wine_gui_contract.py` | PE classification, installer/Electron precedence, process identity, survival/death, verification policy, setup API, dotnet skip |
| `tests/pe_test_helpers.py` | Minimal PE subsystem fixtures |
| `tests/test_profile_shadow.py` | Run F reconstruction blocked when reuse disabled (unchanged) |

**Focused results:** 15 passed (wine GUI + Run F invariant), 18.8s

**Full suite (2026-07-13):** **560 passed, 0 failed** in 1122s (18m42s)

---

## 7. SETUP run results (post-contract)

All four runs via `scripts/validation/pilot002_setup_preflight.py` — **PASS**, no operator interaction.

| Setup ID | Success | Phase | Policy | Session ID | Candidate ID | Profile ID | Trust |
|----------|---------|-------|--------|------------|--------------|------------|-------|
| SETUP-T2-A | ✓ | `wine_gui` | `wine_gui_process_v1` | `17f9b055-4ced-454f-b604-c2e7be12c266` | `18d9dff1-4df8-4cc4-87e7-73baefdba9db` | `425f8664-7ddd-4a99-b984-435051027e8f` | `locally_verified` |
| SETUP-T2-B | ✓ | `wine_gui` | `wine_gui_process_v1` | `1599d04a-04fd-4a3f-82a9-1cf68b379c90` | `36b890d8-9ac3-4751-ade6-7e4d42a442e0` | `bebf5c5f-6719-4ac2-8e75-29ac6c839bf3` | `locally_verified` |
| SETUP-T3-A | ✓ | `wine_gui` | `wine_gui_process_v1` | `09581544-85d9-4023-8a3f-38dfab21150b` | `1262a6d7-163a-45e1-ad1a-065f0d3c0cad` | `6aec0dd2-e298-4173-aec3-603e2aae691b` | `locally_verified` |
| SETUP-T3-B | ✓ | `wine_gui` | `wine_gui_process_v1` | `016a1fb2-3b07-404c-a13d-3d38947bf01b` | `33734800-eee2-4d54-a87f-1ca0acb5e271` | `9b0cf7ff-aca8-44ee-b354-28505ac3c60d` | `locally_verified` |

Checks on all runs: `process_survives`, `target_process_identity`.

**write.exe:** remains diagnostic/fallback only (`write-fallback` setup ID).

---

## 8. Confirmations

| Constraint | Status |
|------------|--------|
| No CompatibilityProfile/shadow/ranking/lifecycle/reuse behavior changes | ✓ (execution + verification only) |
| Active reuse disabled | ✓ |
| Run F reconstruction blocked | ✓ invariant test passes |
| Pilot-002 scenario runs not executed | ✓ |
| No freeze commit created | ✓ |
| No manual GUI closure | ✓ |

---

## 9. Revised freeze package

See `data/validation/campaigns/pilot-002-freeze-package.md` — update SETUP-T2/T3 status to **PASS** before operator re-approval.

**Blocker cleared:** Wine GUI execution/verification contract resolved. Freeze package may proceed to operator review (commit still withheld until requested).

---

## 10. Full suite

```bash
cd /home/joshua/Desktop/Alma/alma-bridge && . .venv/bin/activate && python -m pytest -q
```

| Run | Passed | Failed | Duration |
|-----|--------|--------|----------|
| Prep (`0f91cae`) | 545 | 0 | — |
| Post Wine GUI contract (2026-07-13) | **560** | **0** | 1122s |
