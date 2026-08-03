# Security Model — Architecture Deep-Dive

**Status:** As-built (`SECURITY.md`, `api/auth.py`, audit R5)  
**Scope:** On-premise K-12 lab deployment model documented in repository

## Threat model assumptions

Alma Bridge defaults to:

- Bind `127.0.0.1:9010` (`config.py`)
- No API key required for local development
- SQLite data under configurable `data/` directory on district-controlled infrastructure

Documentation explicitly warns against exposing ports 9010 or 9002 to the public internet without TLS and access controls (`SECURITY.md`).

## Authentication

`ApiKeyMiddleware` (`api/auth.py`) gates mutating endpoints when `ALMA_BRIDGE_API_KEY` is set:

- Header `X-API-Key: <secret>`, or
- Header `Authorization: Bearer <secret>`

Protected paths include `/bridge/run`, modernization apply, automation run/approve/agent, container run, import/train/export, TLS bridge start, autopilot run, compliance data purge (`SECURITY.md` list).

**Default:** `api_key=None` → mutating endpoints open on localhost (R5).

Read-only assess, health, playbook preview, and platform GET routes remain unauthenticated for monitoring UIs.

## Authorization and mutation gates

Beyond API key:

| Gate | Location | Behavior |
|------|----------|----------|
| Campaign guard | `validation/campaign_guard.py` | May return 403 on `/bridge/run` for campaign prefixes |
| Modernization apply | `api/routes.py` | Requires `allow_mutations=true` else 400 |
| Automation apply | `automation/runner.py` | Requires `allow_mutations` or valid `approval_token` |
| PolicyGate | `session/policy.py` | Approves `ActionIntent` before prefix mutation |
| prefix_lock | `session/prefix_lock.py` | `fcntl.flock` serializes prefix writes |
| Autopilot execute | `compliance/autopilot.py` | Dry-run default; mutating steps returned as plan only |

## Data privacy

- No student PII collected by default (FERPA/COPPA notes in `SECURITY.md`)
- Automation audit logs redact sudo passwords and approval tokens (`compliance/program.redact_request_payload` used in automation runner)
- Retention default 365 days; purge via `DELETE /compliance/program/data`

## Network egress

Compliance probes (TLS assess, service scan, web3 assess, DoH) perform outbound connections to **operator-supplied targets**. Restricting API access limits abuse (`SECURITY.md`).

## CORS

Hardcoded dev origins in `main.py`: ports 9002, 3000, 3001 (R5). Deploy-time configuration would be cleaner per audit recommendation.

## Observability

Prometheus metrics at `GET /metrics` (`observability/prometheus.py`) — read-only export.

## Certifications (documented status)

| Standard | Status per SECURITY.md |
|----------|------------------------|
| FERPA (DPA) | Documented — execute with district |
| COPPA | Not child-directed |
| SOC 2 Type II | Not yet — on-prem model |

## Read-only platform tier security property

Platform packages cannot invoke execution even if HTTP layer were misconfigured — import boundary tests fail the build on forbidden dependencies. This is defense-in-depth, not a substitute for network isolation.

## Vulnerability reporting

Private disclosure to maintainer; no public issues for unfixed security bugs (`SECURITY.md`).

## Related documents

- [SECURITY.md](../../../SECURITY.md)
- [ARCHITECTURE_REPORT.md](../../architecture/ARCHITECTURE_REPORT.md) R5
- [API_BOUNDARIES.md](../../architecture/API_BOUNDARIES.md) §3
