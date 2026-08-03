# Capability Behavior Profiles

ACI Phase 2 distinguishes **API availability** (import symbol resolved and
classified) from **API behavior** (specific semantics the binary requests).

## Problem

Static PE analysis sees `kernel32.dll!WriteFile` and `kernel32.dll!CreateFileW`
imports. Symbol coverage reports 100% when both APIs are classified as
`filesystem.basic_io` with `native=supported`. However, the binary may request
behaviors the native shim does not implement — e.g., append-to-existing file
via `OPEN_EXISTING` + `FILE_APPEND_DATA`.

Without behavior profiles, ACI would assign `very_high` confidence to a binary
that will fail at runtime despite perfect symbol coverage.

## CapabilityBehaviorProfile

```python
CapabilityBehaviorProfile(
    capability_id="filesystem.basic_io",
    provider_id="native_alma",
    implementation_version="0.2.0-m2",
    supported_behaviors=["create_always_write", "sequential_read"],
    unsupported_behaviors=["append_existing_file", "overlapped_io"],
    limitations=["OPEN_EXISTING without CREATE_ALWAYS not fully supported"],
    verified_scenarios=["file_write_fixture", "file_read_fixture"],
    evidence_references=[...],
)
```

## Behavior detection

`behavior_requirements.py` inspects PE metadata and import patterns to infer
required behaviors:

| Import pattern | Inferred behavior |
|----------------|-------------------|
| `CreateFileW` + `CREATE_ALWAYS` | `create_always_write` |
| `CreateFileW` + `OPEN_EXISTING` | `open_existing_readwrite` |
| `CreateFileW` + `FILE_APPEND_DATA` access | `append_existing_file` |
| `WriteFile` with non-null overlapped | `overlapped_io` |
| `GetEnvironmentVariableW` | `read_environment_variable` |
| `ExitProcess` | `process_exit_with_code` |

Behavior inference is deterministic and conservative — unknown patterns add to
`unresolved_dynamic_behavior_count` rather than assuming support.

## Coverage levels (multi-dimensional)

Do not collapse dimensions into a single score:

| Dimension | Measures |
|-----------|----------|
| `symbol_coverage` | Classified imports / total imports |
| `capability_coverage` | Supported capabilities / required capabilities |
| `behavior_coverage` | Supported behaviors / required behaviors |
| `verified_scenario_coverage` | Verified scenarios / applicable scenarios |
| `unknown_api_count` | Unclassified imports |
| `unresolved_dynamic_behavior_count` | Behaviors that cannot be statically resolved |

## Confidence impact

When `behavior_coverage < symbol_coverage`, confidence is penalized even if
symbol coverage is 100%. The penalty is explainable via `confidence.factors`.

## Behavioral test fixture

`file_append_unsupported.exe` deliberately:

1. Imports `CreateFileW` and `WriteFile` (symbols supported)
2. Requests `append_existing_file` behavior (unsupported on native_alma)
3. Static symbol coverage remains 100%
4. Behavior coverage identifies the gap
5. Prediction confidence must not remain `very_high`
6. Execution fails closed or verifies failure
7. Calibration exposes `filesystem_semantics_gap` attribution

Build: `tests/fixtures/native_runtime/src/file_append_unsupported.c`
