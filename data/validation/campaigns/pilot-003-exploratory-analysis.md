# Pilot-003 Exploratory Analysis (Preserved)

Raw records under `data/validation/evidence/pilot-003/` are unchanged.

## Valid Exploratory Findings (Not Promotion Evidence)

| Run | Finding |
|-----|---------|
| 1–3 | Stable T2 profile selection; relocated executable identity stable |
| 3 | Compatible host drift selected canonical profile |
| 8 | Run F shadow-only: reuse disabled, `reconstruction_required`, no active reconstruction |
| 11 (shadow) | Imported fixture `winner_selectable=0`; canonical T2 selected |
| All | Source snapshot integrity maintained; export redaction passed |

## Invalid for Promotion Evidence

| Run | Reason |
|-----|--------|
| 4–5 | `HOST_ARCH_MISMATCH` from post-hoc overlay only — not immutable pre-plan prediction |
| 6 | Windows-version drift not induced (`win10` observed; manifest unchanged) |
| 7 | Component drift not induced (executor added corefonts vs remove) |
| 9 | Known failure scenario succeeded (WordPad launched) |
| 11 (label) | Invalid label type aborted campaign |

## Duplicate Metric Note

Partial campaign reported `profile_creation_duplicate_rate=0.55`. Root cause: comparison metric treated any co-occurrence of shadow winner + profile candidate as duplicate. Corrected in Pilot-004 engineering (see `profile_shadow_comparison.py`).

## DB Preservation

Final DB `d8561a48…` retains imported trust mutation on `425f8664…` for audit. Do not restore.
