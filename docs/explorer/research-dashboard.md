# Research Dashboard — Explorer Panel

Analytical-only dashboard in **almasysdet** for Alma Research Platform v1.

## Route

`/research` — nav link **Research** in `App.js`

## Files

| File | Role |
|------|------|
| `alma-frontend/src/components/ResearchDashboardPanel.jsx` | Dashboard UI |
| `alma-frontend/src/api/researchClient.js` | Bridge API client |
| `alma-frontend/src/api/researchModel.js` | View models |

## API endpoints consumed

- `GET /bridge/research/reports` — report catalog
- `GET /bridge/research/dashboard` — aggregated dashboard
- `GET /bridge/research/reports/{report_type}` — individual report drill-down

## UI sections

- Top unsupported behaviors, calibration gaps, unknown APIs
- Capability maturity growth
- Prediction accuracy trends
- Native runtime growth
- Governance velocity and expansion backlog
- Verification trends
- Sample sizes (`n=`) and limitations on every metric

## Constraints

- Read-only GET — no apply, no execution
- Limitations surfaced prominently
- No causation language in displayed summaries
