# Runtime Conformance

Phase 0B establishes a **non-authoritative conformance foundation** for
comparing runtime provider behavior against baselines.

## Classifications

| Classification | Meaning |
|----------------|---------|
| `equivalent` | Matching exit code and stdout |
| `functionally_equivalent` | Matching exit code, different stdout |
| `partially_equivalent` | Overlapping evidence signals |
| `behavior_changed` | Different exit codes |
| `candidate_failed` | Candidate provider failed or is fail-closed |
| `insufficient_evidence` | Required signals missing |

## Components

```
runtime/conformance/
├── models.py      # ConformanceScenario, ConformanceRunResult, ConformanceReport
├── scenarios.py   # Built-in scenario catalog
├── comparison.py  # classify_baseline_comparison()
├── runner.py      # ConformanceRunner (inspect/prepare only in Phase 0B)
├── repository.py  # In-memory report storage
└── service.py     # ConformanceService suite runner
```

## Phase 0B scope

- Inspect/prepare-only checks (no orchestrator integration)
- Default scenarios: wine vs proton, container vs wine, native_alma fail-closed
- Does **not** declare verified session success
- Does **not** replace VerificationEngine authority

## Future work

- Persist conformance reports alongside session evidence
- Attach conformance artifacts to regression intelligence (ADR-005 pattern)
- Expand scenarios as native Alma runtime matures

## Usage

```python
from alma_bridge.runtime.conformance.service import ConformanceService

service = ConformanceService()
report = service.run_default_suite(file_path="/path/to/app.exe")
```
