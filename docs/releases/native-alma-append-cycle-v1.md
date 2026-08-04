# Native Alma Append Cycle v1 — Engineering Release

**Tag candidate:** `alma-native-append-v1`  
**Work item:** `wi_native_alma_filesystem_basic_io_append_existing_file_v1`  
**Provider:** `native_alma`  
**Shim version:** `0.2.1-m2`  
**Cycle commits:** `1091a98` → `f405546` (+ audit hardening)

## Scope

Bounded workspace-confined synchronous append via `CreateFileW(OPEN_EXISTING, FILE_APPEND_DATA)` and
`WriteFile` for PE64 console binaries. Eight new append fixtures plus historical
`file_append_unsupported.exe` transition.

## Security

- Path traversal rejected at resolver and fixture level
- Overlapped I/O remains unsupported (`ERROR_NOT_SUPPORTED`)
- No Wine delegation for append
- Anti-simulation: `simulation_used=false` on all append fixtures

## Fixture Digests

See `tests/fixtures/native_runtime/manifest.json` (17 PE fixtures).

Append matrix (8):

| Fixture | SHA-256 (prefix) |
|---------|------------------|
| append_existing_success.exe | `5da741e4…` |
| append_repeated.exe | `223cc800…` |
| append_unicode.exe | `deebad61…` |
| append_zero_length.exe | `886ca130…` |
| append_invalid_handle.exe | `bf558239…` |
| append_missing_file.exe | `a53cf636…` |
| append_path_traversal.exe | `e85503be…` |
| append_overlapped_unsupported.exe | `7f870d43…` |

## Test Results

Reproduce with:

```bash
scripts/reproduce_append_cycle.sh
```

Targeted append/platform suites: 276+ tests. Full backend suite collects without errors
(`--import-mode=importlib` resolves duplicate test module basenames).

## Verification

Semantic verification contract checks:

- Initial file existed; original bytes preserved
- Payload appended once; final size correct
- Workspace confined; no external files
- `simulation_used=false`, provider `native_alma`, version `0.2.1-m2`

Negative control: altering expected preserved byte invalidates verification (see audit tests).

## Calibration

Historical gap fixture `file_append_unsupported.exe` resolves under updated behavior profile.

## Certification

Review requested; behavior **not auto-certified**. Evidence in
`docs/certification/append_existing_file_evidence.md`.

## Governance

Proposal `gov_proposal_append_existing_file_v1` pending human review.
`governance_disposition=pending` is allowed at `completed` engineering status.

## Completion Policy

- **engineering_complete:** implementation, tests, security, conformance, benchmarks, verification, calibration, certification review
- **workflow_completed:** governance disposition resolved (approved/rejected/deferred/not_required)

Engineering completion does not require governance promotion.

## Benchmarks

Reproducible baselines: warmup=3, iterations=10, median/min/max/mean/stddev/MAD.
Host metadata: arch, CPU, kernel, compiler, shim version, fixture digest.

## Evidence Manifest

Committed at `data/native_lab/evidence_manifest.json` (17 references).

## Limitations

- Synchronous append only; `overlapped_io` unsupported
- Workspace-relative paths only
- PE64 console subsystem
- Governance registry promotion pending

## Reproduction Commands

```bash
git worktree add /tmp/alma-append-audit-clean f405546
cd /tmp/alma-append-audit-clean
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
bash tests/fixtures/native_runtime/build_fixtures.sh
pytest tests/release/test_append_cycle_audit.py -q
pytest -q
```
