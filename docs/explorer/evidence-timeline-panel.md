# Compatibility Evidence Timeline Explorer Panel

Unified lifecycle view in **almasysdet** — one continuous evidence pipeline instead of jumping between tabs.

## Route

`/evidence-timeline` → `CompatibilityTimelinePanel.jsx`

## Features

- **Lifecycle timeline** — Analyzed → Predicted → Executed → Verified → Knowledge → Regression → Decision → Review → Validation → Capability Promotion → Expansion Planning
- Every stage links to evidence digest and source subsystem
- **Platform dashboard** — native coverage, behavior coverage, prediction precision/recall, calibration accuracy, governance proposals, expansion backlog (all with sample sizes)
- **Capability evolution** — maturity states from governance registry with supported/unsupported behaviors
- **Bundle history** — version replay for old predictions retaining old registry interpretation
- Default fixture path: `hello64.exe` (configurable via `REACT_APP_HELLO64_PATH`)

## API client

`evidenceClient.js`:

- `fetchEvidenceBundleByDigest(binaryDigest)`
- `fetchEvidenceBundleByFingerprint(fingerprint)`
- `fetchEvidenceTimeline(bundleId)`
- `fetchEvidenceHistory(bundleId)`
- `fetchPlatformHealth()`
- `assembleEvidenceBundle({ filePath, binaryDigest, sessionId })`

## View model

`evidenceModel.js`:

- `buildTimelineView`
- `buildBundleSummary`
- `buildPlatformHealthView`
- `buildCapabilityEvolutionView`
- `stageLabel` / `stageTone`

## almasysdet commit status

Frontend source changes live in the almasysdet working tree. Commit to almasysdet separately when the Explorer repo is ready. Bridge-side documentation is in this file.
