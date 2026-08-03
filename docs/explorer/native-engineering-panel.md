# Native Runtime Engineering Explorer Panel

Explorer UI extension in **almasysdet**
(`alma-frontend/src/components/NativeEngineeringDashboardPanel.jsx`).

Route: `/native-engineering`

## Features

- **API engineering profiles** — spec digest, capability, behavior IDs, suite case count
- **Behavior coverage** — supported/unsupported per behavior with test status
- **Performance trends** — longitudinal benchmark history (read-only)
- **ABI conformance** — check status per category
- **Calibration / governance link counts** per API (read-only aggregates)

## API client

`nativeEngineeringClient.js`:

- `fetchNativeEngineeringApis()`
- `fetchNativeEngineeringProfile(apiSymbol)`
- `fetchNativeEngineeringBehaviors()`
- `fetchNativeEngineeringBenchmarks()`
- `fetchNativeEngineeringConformance()`
- `fetchNativeEngineeringDashboard()`

## View model

`nativeEngineeringModel.js`:

- `buildNativeEngineeringDashboardView`
- `statusTone` / `statusLabel`

## Constraints

- Read-only display — no binary execution from dashboard
- Benchmark history populated only after explicit pytest/CLI benchmark runs
- Governance and calibration displayed as link counts; full records via ACI/Evidence panels

## almasysdet commit status

Frontend source committed to almasysdet on branch `main` alongside this documentation.
