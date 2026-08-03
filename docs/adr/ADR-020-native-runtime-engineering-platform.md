# ADR-020: Native Runtime Engineering Platform

## Status

Accepted — 2026-08-02

## Context

NativeAlmaRuntime M2 delivers real PE64 load and kernel32 shims
([ADR-016](ADR-016-native-console-runtime-milestone-2.md)). ACI Phases 1–4
provide behavior profiles, calibration, governance, and expansion planning
([ADR-017](ADR-017-compatibility-prediction-calibration.md) through
[ADR-019](ADR-019-capability-guided-runtime-expansion.md)). Alma v2.0 evidence
and the Research Platform aggregate compatibility intelligence read-only.

Operators still lack a **single engineering view per Win32 API**: deterministic
specification, behavioral test coverage, benchmark history, and links to
calibration and governance — without executing binaries from dashboard GET
endpoints.

## Decision

Introduce **Native Runtime Engineering Platform v1** under
`alma_bridge/native_engineering/`:

### 1. ApiEngineeringProfile

Each implemented kernel32 API has a profile linking capability/behavior IDs,
deterministic spec, behavior test suite, calibration history (read-only),
governance maturity (read-only), performance metrics, and evidence references.

### 2. Deterministic specifications

`specifications.py` defines params, return values, error modes, and
supported/unsupported behaviors. Symbol export in the C shim does not imply
full behavioral conformance.

### 3. Behavior test suites

`behavior_suites.py` maps scenarios to fixtures in
`tests/fixtures/native_runtime/`. Negative fixture
`file_append_unsupported.exe` documents unsupported append behavior.

### 4. Benchmarks and longitudinal tracking

Benchmark runners (pytest/CLI only) record timing and correctness. Results
append to an immutable history store via `longitudinal.py` and `repository.py`.

### 5. Validation categories

Semantic, memory, handle lifecycle, filesystem, Unicode, and threading
(threading marked `not_applicable` for M2 single-threaded worker).

### 6. Read-only HTTP API

Routes under `/bridge/native-engineering/*` — GET only, no binary execution.

### 7. Explorer dashboard

Alma Explorer panel at `/native-engineering` in almasysdet for behavior
coverage, test status, performance trends, governance, calibration, and
evidence links.

## Consequences

- Every M2 shim API is measurable and engineerable through dashboards
- Benchmark execution remains explicit (pytest/CLI), not HTTP-triggered
- Governance and calibration remain authoritative; engineering platform reads only
- No auto-implementation of Win32 APIs or capability promotion

## References

- [native-runtime-engineering.md](../architecture/native-runtime-engineering.md)
- [native-runtime-behavior-suites.md](../testing/native-runtime-behavior-suites.md)
- [native-alma-runtime roadmap](../roadmap/native-alma-runtime.md)
- [ADR-016](ADR-016-native-console-runtime-milestone-2.md)
- [ADR-019](ADR-019-capability-guided-runtime-expansion.md)
