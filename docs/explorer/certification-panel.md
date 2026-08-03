# Runtime Certification Explorer Panel

Explorer UI extension in **almasysdet**
(`alma-frontend/src/components/CertificationDashboardPanel.jsx`).

Route: `/certification`

## Features

- **Certified APIs** — behavior-scoped certification levels per capability
- **Certification timeline** — historical evolution append-only
- **Behavior matrix** — compliance matrix with coverage and verification %
- **Evidence links** — bundles, fixtures, calibration, governance references
- **Requires Revalidation** — stale items with deterministic reasons
- **Known limitations** — unsupported behaviors with documented gaps

## API client

`certificationClient.js`:

- `fetchCertificationBehaviors()`
- `fetchCertificationProfile(capabilityId, behaviorId)`
- `fetchCertificationMatrix()`
- `fetchCertificationHistory(capabilityId, behaviorId)`
- `fetchCertificationStale()`
- `fetchCertificationDashboard()`

## View model

`certificationModel.js`:

- `buildCertificationDashboardView`
- `certificationLevelTone` / `certificationLevelLabel`

## Constraints

- Read-only display — no binary execution from dashboard
- Certification levels computed from evidence; no auto-promotion
- Governance and calibration displayed as references; full records via ACI/Evidence panels

## almasysdet commit status

Frontend source committed to almasysdet on branch `main` alongside this documentation.
