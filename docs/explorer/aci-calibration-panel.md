# ACI Prediction Calibration Explorer Panel

Explorer UI extension in **almasysdet** (`alma-frontend/src/components/CompatibilityIntelligencePanel.jsx`).

## Features

- **Static prediction** section labeled "Statically predicted — not verified"
- **Multi-dimensional coverage**: symbol, capability, behavior, verified scenario
- **Prediction calibration** panel with sample sizes (numerator/denominator)
- Historical true/false positive rates by classification
- Behavior gap and failure attribution display
- Pre-execution vs post-execution distinction preserved

## API client

`compatibilityIntelligenceClient.js` adds:

- `fetchCalibrationMetrics(providerId?)`
- `fetchCapabilityCalibration(capabilityId)`
- `fetchAnalysisCalibration(analysisDigest)`

## View model

`compatibilityIntelligenceModel.js` adds:

- `buildCalibrationView`
- `buildCoverageDimensionsView`
- `classificationLabel`

## Constraints

- Never labels static prediction as verified before execution
- Read-only GET endpoints only — no execution from Explorer
