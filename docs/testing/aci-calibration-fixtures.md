# ACI Calibration Fixtures

Test fixtures for prediction calibration and behavioral capability coverage.

## Fixture matrix

| Fixture | Capabilities | Behaviors | Expected calibration |
|---------|-------------|-----------|---------------------|
| `hello64.exe` | console.stdout, process.exit | write_stdout, process_exit | true_positive (native) |
| `file_write.exe` | filesystem.basic_io | create_always_write | true_positive (native) |
| `file_read.exe` | filesystem.basic_io | sequential_read | true_positive (native) |
| `environment_read.exe` | process.environment | read_environment_variable | true_positive (native) |
| `exit_code.exe` | process.exit | process_exit_with_code | true_positive (native) |
| `file_append_unsupported.exe` | filesystem.basic_io (symbols) | append_existing_file (unsupported) | false_positive gap exposed |

## Behavioral gap fixture

`file_append_unsupported.c` opens an existing file with `OPEN_EXISTING` and
`FILE_APPEND_DATA`, then writes appended content. Native Alma shim supports
`CreateFileW`/`WriteFile` symbols but does not implement append semantics.

Expected ACI behavior:

- Symbol coverage: 100% for `filesystem.basic_io`
- Behavior coverage: gap on `append_existing_file`
- Confidence: below `very_high`
- Calibration: `false_positive` with `filesystem_semantics_gap` attribution

## Building fixtures

```bash
cd tests/fixtures/native_runtime
./build_fixtures.sh
```

Requires `x86_64-w64-mingw32-gcc`. Updates `manifest.json` with SHA-256 digests.

## Test scenarios (22)

Located in `tests/compatibility_intelligence/calibration/`:

1. Prediction snapshot immutable
2. Snapshot binds exact binary digest
3. Snapshot binds provider capability version
4. Verified success → true_positive
5. Verified failure after eligible → false_positive
6. Unverifiable → indeterminate
7. Ineligible + verified success → false_negative
8. Unknown gap stays unknown
9. Failure attribution requires evidence
10. Static symbol ≠ full behavior support
11. Behavior coverage calculated correctly
12. Sample sizes exposed with rates
13. Old predictions use old registry versions
14. Application A cannot calibrate B
15. Provider A cannot calibrate B
16. No execution in calibration GET endpoints
17. Calibration cannot mutate provider registry
18. Calibration cannot bypass VerificationEngine
19. Native fixture predictions link to native outcomes
20. Wine predictions link to Wine outcomes
21. Deterministic inputs → deterministic calibration
22. Explorer preserves prediction vs verification distinction

## End-to-end acceptance

- `hello64.exe` → statically predicted eligible → verified success → true_positive
- `file_append_unsupported.exe` → behavior gap → prediction not very_high →
  verified failure → false_positive with filesystem_semantics_gap
