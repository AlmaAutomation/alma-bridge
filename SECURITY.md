# Security

Alma Bridge is designed for **on-premise K-12 lab deployment**. Default install binds to localhost and does not require authentication.

**Commercial compliance pack:** [docs/COMPLIANCE.md](../docs/COMPLIANCE.md) · API: `GET /compliance/program`

## Network exposure

- Bind Bridge to `127.0.0.1` unless serving a trusted lab VLAN.
- Do not expose ports 9010 or 9002 to the public internet without TLS termination and access controls.
- Compliance probes (TLS assess, service scan) perform outbound connections to user-supplied targets — restrict who can reach the API.

## Privacy (FERPA / COPPA)

- **No student PII** collected by default
- Automation audit logs **redact** sudo passwords and approval tokens before storage
- Data remains on district-controlled infrastructure (SQLite under `data/`)
- See [Privacy Policy](../docs/legal/PRIVACY_POLICY.md) and [DPA](../docs/legal/DATA_PROCESSING_ADDENDUM.md)

## Data retention

- Default: **365 days** for automation audit sessions (`ALMA_BRIDGE_COMPLIANCE_DATA_RETENTION_DAYS`)
- Purge: `DELETE /compliance/program/data` (requires API key when configured)

## API key (recommended for production)

Set in `.env`:

```bash
ALMA_BRIDGE_API_KEY=<long-random-secret>
```

When configured, the following **mutation** endpoints require:

- Header `X-API-Key: <secret>`, or
- Header `Authorization: Bearer <secret>`

Protected paths include:

- `/bridge/run`
- `/modernization/apply`, `/modernization/windows/apply`
- `/automation/run`, `/automation/approve`, `/automation/agent/*`
- `/container/run`
- `/import/*`, `/train/ranker`, `/datasets/export`
- `/compliance/tls/bridge`, `/compliance/autopilot/run`
- `/compliance/program/data` (purge)

Read-only assess, health, playbook preview, and compliance program endpoints remain open for monitoring UIs.

Leave `ALMA_BRIDGE_API_KEY` unset for local development.

## Sudo and host mutations

Apply and automation endpoints can run **allowlisted** package manager and system commands with sudo. Use:

- Approval tokens (`POST /automation/approve`)
- Confirmation in the UI
- Network isolation so only IT staff reach mutation endpoints

Never expose sudo password fields over untrusted networks. Passwords are not stored in audit logs.

## Data storage

- Session and outcome data: SQLite under `data/` (configurable via `ALMA_BRIDGE_DATA_DIR`)
- Automation sessions: separate tables in the same data directory
- No student PII is collected by default; scan paths are operator-defined

## Certifications

| Standard | Status |
|----------|--------|
| FERPA (DPA) | Documented — execute with district |
| COPPA | Not child-directed |
| SOC 2 Type II | Not yet — on-prem model |

## Reporting vulnerabilities

Contact the project maintainer privately with reproduction steps. Do not open public issues for unfixed security bugs.
