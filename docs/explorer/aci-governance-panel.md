# ACI Capability Governance Explorer Panel

Explorer UI extension in **almasysdet**
(`alma-frontend/src/components/CompatibilityIntelligencePanel.jsx`).

## Features

- **Capability governance** section with scope-aware maturity display
- Provider, capability, behavior profile, and fixture scope per entry
- Current vs proposed maturity with calibration sample sizes
- Supported vs unsupported behaviors shown separately (no generic "supported" badge)
- False-positive counts and limitations surfaced per proposal
- Review history (approved / rejected / needs_revision)
- Registry version binding visible in UI

## API client

`compatibilityIntelligenceClient.js` adds:

- `fetchGovernanceProposals(limit?)`
- `fetchGovernanceProposal(proposalId)`
- `fetchGovernanceRegistry()`
- `createGovernanceProposal(payload)`
- `reviewGovernanceProposal(proposalId, payload)`
- `applyGovernanceProposal(proposalId, payload)`

## View model

`compatibilityIntelligenceModel.js` adds:

- `buildGovernanceView`
- `maturityLabel` / `maturityTone`

## Constraints

- Read-only display by default; create/review/apply via explicit API calls only
- Never labels capability as globally stable from bounded fixture evidence
- No execution from governance endpoints
- Human approval required before registry mutation

## almasysdet commit status

Frontend source changes live in the almasysdet working tree alongside this
documentation. Commit to almasysdet separately when the Explorer repo is ready.
