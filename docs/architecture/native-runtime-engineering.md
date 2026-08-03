# Native Runtime Engineering Platform

Deterministic engineering layer for **NativeAlmaRuntime M2**. Every implemented
Windows API is measurable and engineerable through specifications, behavioral
test suites, benchmarks, conformance reports, calibration links, governance
status, and evidence references.

## Purpose

Native runtime shims in `alma_bridge/native_runtime/shim/` implement a bounded
kernel32 surface. The engineering platform (`alma_bridge/native_engineering/`)
does **not** execute binaries on GET endpoints. It aggregates read-only
engineering metadata and runs benchmarks only via pytest or explicit CLI.

## Core model: ApiEngineeringProfile

For each implemented Win32 API symbol, an `ApiEngineeringProfile` links:

| Field | Source |
|-------|--------|
| `capability_id`, `behavior_id` | ACI `behavior_requirements.py` |
| Deterministic specification | `specifications.py` |
| Behavioral test suite | `behavior_suites.py` + fixtures |
| Calibration history | `CalibrationRepository` (read-only) |
| Governance status | `GovernanceRepository` (read-only) |
| Performance metrics | `benchmarks.py` + `longitudinal.py` |
| Evidence references | `evidence/` bundles, fixture paths |

## Package layout

```
alma_bridge/native_engineering/
├── models.py              # ApiEngineeringProfile, BenchmarkResult, etc.
├── specifications.py      # Deterministic API specs
├── behavior_suites.py       # Per-API behavior scenarios
├── benchmarks.py            # Performance + correctness runners
├── conformance.py           # ABI conformance reports
├── semantic_validation.py   # API semantic validation
├── memory_tests.py          # Memory correctness definitions
├── handle_lifecycle.py      # Handle lifecycle validation
├── filesystem_semantics.py  # Filesystem semantic validation
├── unicode_validation.py    # Unicode correctness validation
├── threading_validation.py  # Multi-thread (deferred / not_applicable)
├── longitudinal.py          # Append-only benchmark history
├── repository.py            # Persist specs, results, history
├── dashboard.py             # Aggregated dashboard data
├── queries.py               # Read-only profile queries
└── service.py               # Orchestration
```

## Validation categories

- **API semantic validation** — return values, error modes, unsupported behaviors
- **Memory correctness** — buffer bounds, UTF-16 handling
- **Handle lifecycle** — open/close, invalid handle rejection
- **Filesystem semantics** — sandbox paths, CREATE_ALWAYS vs append unsupported
- **Unicode correctness** — wide-char environment and command line
- **Multi-thread behavior** — marked `not_applicable` for single-threaded M2 worker

## Integration

- ACI behavior profiles: `compatibility_intelligence/behavior_requirements.py`
- Calibration: `calibration_repository.py` (immutable snapshots, read-only links)
- Governance: `governance/repository.py` (maturity per scope, no auto-promotion)
- Evidence: `evidence/` CompatibilityEvidenceBundle digests
- Research: optional aggregate metrics via `research/queries.py`

## HTTP API (read-only GET)

| Endpoint | Description |
|----------|-------------|
| `GET /bridge/native-engineering/apis` | List API engineering profiles |
| `GET /bridge/native-engineering/apis/{api_symbol}` | Full profile |
| `GET /bridge/native-engineering/behaviors` | Behavior coverage dashboard |
| `GET /bridge/native-engineering/benchmarks` | Benchmark results + history |
| `GET /bridge/native-engineering/conformance` | ABI conformance report |
| `GET /bridge/native-engineering/dashboard` | Aggregated engineering dashboard |

Benchmark execution is **not** triggered by GET. Use pytest or
`python -m alma_bridge.native_engineering.benchmarks` explicitly.

## Boundaries (MUST NOT)

- Change runtime selection heuristics without evidence
- Change VerificationEngine authority
- Auto-promote capabilities or mutate governance history
- Execute binaries from GET/read/dashboard endpoints
- Use AI/LLM or auto-implement Win32 APIs

## References

- [native-alma-runtime-m1.md](native-alma-runtime-m1.md)
- [native-runtime-behavior-suites.md](../testing/native-runtime-behavior-suites.md)
- [ADR-020](../adr/ADR-020-native-runtime-engineering-platform.md)
- [native-alma-runtime roadmap](../roadmap/native-alma-runtime.md)
