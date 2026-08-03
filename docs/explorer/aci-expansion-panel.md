# ACI Runtime Expansion Explorer Panel

Explorer UI extension in **almasysdet**
(`alma-frontend/src/components/CompatibilityIntelligencePanel.jsx`).

## Features

- **Runtime expansion planning** section with top bounded engineering candidates
- Observed demand, estimated bounded impact, complexity, security risk, and
  testability shown distinctly
- Prerequisites and registry limitations surfaced per candidate
- [View evidence] links to evidence references (fixture, shim, calibration)
- Clearly labeled advisory — no "Implement now", "Auto-generate", or "Apply patch"

## API client

`compatibilityIntelligenceClient.js` adds:

- `fetchExpansionPlan(filters?)`
- `fetchExpansionCandidate(candidateId)`
- `fetchExpansionCandidatesForCapability(capabilityId)`

## View model

`compatibilityIntelligenceModel.js` adds:

- `buildExpansionView`
- `complexityLabel` / `complexityTone`

## Constraints

- Read-only display; plan generation does not execute binaries or mutate registry
- Impact language uses "estimated bounded impact" and "identified blocker"
- Human engineering judgment required before any implementation

## almasysdet commit status

Frontend source changes live in the almasysdet working tree alongside this
documentation. Commit to almasysdet separately when the Explorer repo is ready.
