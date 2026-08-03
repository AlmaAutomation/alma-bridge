# Native Runtime Laboratory Explorer Panel

## Route

`/native-lab` in almasysdet Alma Explorer.

## Views

| View | Content |
|------|---------|
| Backlog | Work items in `proposed` or `triaged` |
| Active | Items in design through testing |
| Dependency graph | Prerequisites and blocked-by relationships |
| Verification queue | Items in `verification_pending` |
| Certification queue | Items in `certification_pending` |
| Completed | Evidence-gated completed items |
| History | Append-only status event timeline |

## Displayed Fields

- Bounded scope and provider/capability/behavior identifiers
- Observed demand and bounded impact (blocker removal language)
- Current maturity and certification level (read-only from certification platform)
- Owner and reviewer assignments
- Status and blockers
- Checklist progress by category
- Risk review summary
- Evidence freshness (`evidence_stale` indicator)

## Human Actions

The panel supports workflow coordination only:

- View engineering cards and checklists
- Navigate to related evidence and expansion candidates
- Inspect dependency blockers

## Explicitly Excluded

The panel does **not** provide:

- Implement automatically
- Generate patch
- Apply runtime change
- Promote automatically
- Certify automatically

## Components

- `NativeLabDashboardPanel.jsx` — main panel
- `nativeLabClient.js` — API client
- `nativeLabModel.js` — view model builders
