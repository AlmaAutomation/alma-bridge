# Validation diagnostics (non-production)

Scripts and tools in this section are **diagnostic-only**. They are not imported or invoked by `alma_bridge` production code.

## Scripts

| Script | Purpose | Timeouts |
|--------|---------|----------|
| `ascension_baseline_investigate.py` | Disposable Ascension control matrix (C1–C7) | Bounded per control |
| `sidecar_ipc_investigate.py` | Sidecar IPC process tracing + controls P/D/I | `MAX_BRIDGE_SEC=420`, control holds ≤90s |

### Environment

Set campaign/disposable paths before running (see `pilot_env.sh`). Diagnostic scripts accept:

- `ALMA_BRIDGE_VALIDATION_CAMPAIGN_DISPOSABLE_ROOT`
- `ALMA_BRIDGE_VALIDATION_CAMPAIGN_PRIMARY_PREFIX` (read-only guard reference)
- `ALMA_BRIDGE_VALIDATION_CAMPAIGN_SOURCE_SNAPSHOT` (clone source)

Do not point diagnostics at production prefixes you intend to preserve unmodified.

## Tools

| Tool | Location | Production use |
|------|----------|----------------|
| `cs_wrapper_diag.c` | `tools/diagnostics/` | **Never** — investigation-only wrapper variant |

Build locally with mingw-w64; install only into disposable prefixes via `sidecar_ipc_investigate.py --control-d`.

## Cleanup

Always end diagnostic sessions with:

```bash
.venv/bin/python3 scripts/validation/sidecar_ipc_investigate.py --cleanup-only
```
