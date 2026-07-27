# Alma Bridge

**Engine for the [Alma Lab Modernization Program](../docs/flagship-program.md)** — Alma's flagship K-12 offering.

Extend lab PC life 2–3 years without a hardware refresh: assess → playbook → apply → verify on one Linux server, with Windows GPO/PDQ export for lab seats.

Alma Bridge also provides adaptive legacy software execution (Wine, Proton, containers) for advanced use cases.

## Flagship program (start here)

| Step | API / UI |
|------|----------|
| Program metadata | `GET /flagship` |
| Flagship console | http://127.0.0.1:9002/app/compliance |
| Linux recipe | `school-lab` via `POST /automation/run` |
| Windows recipe | `school-lab-windows` + `GET /modernization/windows/export.ps1` |
| Docs | [K-12 deployment](../docs/k12-lab-deployment.md) · [Pilot pricing](../docs/pilot-pricing-sheet.md) |

---

## What Bridge does (technical)

Adaptive compatibility engine for Alma. Alma Bridge unifies legacy software execution, hardware-aware shims, and a closed learning loop that retries failed launches until something works — or exhausts all strategies.

## What it does

- **Detect** binary format (ELF, PE, scripts) and host hardware profile (GPU, drivers, multiarch, memory)
- **Plan** execution strategies: native, Wine, Proton, QEMU, container sandbox
- **Run** programs on the host or inside Docker/Podman containers
- **Classify** failures into signatures (missing DLL, GPU crash, arch mismatch, etc.)
- **Remediate** automatically with env overrides and hardware shims
- **Learn** by recording every attempt in a unified outcome database for future ML ranking

## Architecture

```
Binary + Host Profile
        │
        ▼
  Strategy Planner ──► ML Ranker (historical success rates)
        │
        ▼
  Retry Orchestrator ◄──── Remediation Catalog + Hardware Shims
        │
   ┌────┴────┐
   ▼         ▼
 Host     Container
 Runner    Sandbox
        │
        ▼
  Outcome Store (SQLite) ──► Training Dataset Export
```

## Setup (backend)

Debian/Ubuntu block system-wide `pip` (PEP 668) — use a venv:

```bash
git clone <your-repo-url> alma-bridge && cd alma-bridge
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Optional: copy env template
cp .env.example .env

python -m alma_bridge.main
# API docs: http://127.0.0.1:9010/docs
# Health:    http://127.0.0.1:9010/health
```

With the **Alma Scanner** UI, start this service alongside `almasysdet` on port 9002. The React app reaches Bridge via `/bridge-api` proxy.

### Run a program through the bridge

```bash
curl -X POST http://127.0.0.1:9010/bridge/run \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "/path/to/program",
    "sandbox": true,
    "max_attempts": 8
  }'
```

### Docker stack (API + sandbox image)

```bash
docker compose build
docker compose up -d
```

## API endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Service health |
| `GET /hardware/profile` | Host hardware + capability profile |
| `POST /bridge/plan` | Preview execution strategies without running |
| `POST /bridge/run` | Full adaptive run with retry loop |
| `GET /bridge/session/{id}` | Session attempt history |
| `GET /outcomes/stats` | Aggregate success/failure statistics |
| `GET /outcomes/prior-success?path=` | Last successful run for a binary path |
| `POST /datasets/export` | Export JSONL + CSV for ML training |
| `POST /compliance/tls/assess` | Assess a host's TLS posture vs today's baseline |
| `POST /compliance/tls/bridge` | Start a TLS-modernizing bridge for a legacy client |
| `GET /compliance/tls/bridges` | List active TLS-modernizing bridges |
| `DELETE /compliance/tls/bridge/{id}` | Stop a bridge |
| `GET /compliance/drivers` | Inventory PCI/USB devices + flag missing drivers |
| `POST /compliance/scan` | Unified compliance report (TLS + web3 + drivers + shims) |
| `POST /compliance/web3/assess` | Probe an EVM JSON-RPC endpoint for web3 readiness |
| `GET /compliance/web3/chains` | Known chain-id registry |
| `POST /compliance/web3/ipfs-url` | Rewrite `ipfs://`/`ipns://` to a gateway URL |
| `GET /compliance/tls/ca-bundle` | Download Alma's up-to-date CA root bundle (PEM) |
| `POST /compliance/time/check` | Measure clock skew vs NTP (TLS cert validity) |
| `POST /compliance/services/scan` | Detect legacy insecure services on a host |
| `POST /compliance/dns/resolve` | Resolve a name over DNS-over-HTTPS |
| `POST /compliance/autopilot/diagnose` | Classify an error into ranked diagnoses |
| `POST /compliance/autopilot/run` | Diagnose + plan remediation pathways (self-healing) |
| `POST /compliance/autopilot/feedback` | Teach the autopilot which pathway worked |
| `GET /compliance/autopilot/host` | Host context (arch, package manager) |
| `GET /compliance/legacy32` | Assess 32-bit runtime readiness of the host |
| `POST /compliance/legacy32/plan` | Distro-aware steps to enable 32-bit binaries |

## Relationship to other Alma projects

| Project | Role |
|---------|------|
| **almasysdet** | Binary scanning, static compatibility rules, execution history |
| **alma_resolve** | Wine/Proton launcher recovery scripts and diagnosis |
| **alma-bridge** | Unified orchestrator + learning loop (this project) |

Alma Bridge imports historical audit data from **almasysdet** and **alma_resolve** via `/import/*` endpoints (see `alma_bridge/importers/`).

## Configuration

Copy `.env.example` to `.env` (optional). Environment variables use prefix `ALMA_BRIDGE_`:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_DIR` | `data` | Storage directory |
| `DB_PATH` | `data/outcomes.db` | SQLite database |
| `MAX_ATTEMPTS` | `8` | Max retry attempts per session |
| `EXECUTION_TIMEOUT_SEC` | `120` | Per-attempt timeout |
| `SANDBOX_IMAGE` | `alma-bridge-sandbox:latest` | Container image |
| `SANDBOX_ENABLED` | `true` | Allow container execution |
| `API_HOST` | `127.0.0.1` | API bind address |
| `API_PORT` | `9010` | API port |

## Tests

```bash
source .venv/bin/activate
python -m pytest -q
```

See [`docs/testing.md`](docs/testing.md) for isolation conventions (including
restoring any `sys.modules` manipulation before a test exits).

## Importing legacy Alma data

Pull execution history and recovery audits into the unified outcome store:

```bash
# Import both almasysdet + alma_resolve (default paths)
curl -X POST http://127.0.0.1:9010/import/all \
  -H "Content-Type: application/json" \
  -d '{"skip_existing": true}'

# Import only almasysdet with custom DB path
curl -X POST http://127.0.0.1:9010/import/sysdet \
  -H "Content-Type: application/json" \
  -d '{"sysdet_db": "../almasysdet/data/alma.db"}'
```

Default source paths (override with env vars):

| Variable | Default |
|----------|---------|
| `ALMA_BRIDGE_SYSDET_DB_PATH` | `../almasysdet/data/alma.db` |
| `ALMA_BRIDGE_RESOLVE_AUDIT_DIR` | `../alma_resolve/runtime_data/audit` |

## ASOD hardware integration

`GET /hardware/profile` now merges ASOD-style detection (GPU model, storage type, RAM, swappiness, CPU model) with bridge capability probing. Recommended shims are returned based on `legacy_indicators` such as `low_memory`, `rotational_storage`, and `legacy_or_generic_gpu_driver`.

## Proton + alma_resolve remediations

On failure, the orchestrator now applies alma_resolve recovery profiles before switching strategies:

- Software rendering / GPU process disabled (`--disable-gpu`, DXVK off)
- WineD3D fallback and best-known profile
- Virtual desktop, network workarounds, win32 prefix, multiarch libs

Proton is auto-discovered from Steam compatibility tools. Check installs:

```bash
curl http://127.0.0.1:9010/hardware/profile | python3 -m json.tool
```

## Train the strategy ranker

```bash
curl -X POST http://127.0.0.1:9010/train/ranker
curl http://127.0.0.1:9010/train/ranker/status
```

The ranker trains a `HistGradientBoostingClassifier` on imported bridge attempts and uses it to score candidate strategies during `/bridge/plan` and `/bridge/run`.

## Legacy compliance (HTTPS + drivers/shims)

`alma_bridge/compliance/` brings legacy machines up to modern standards along
two axes, exposed under `/compliance/*`.

### 1. HTTPS / TLS

Old machines frequently can't reach today's HTTPS services: they only speak
TLS 1.0/1.1, ship expired CA roots, or negotiate dead ciphers. Bridge handles
this in two steps.

**Assess** what's wrong with an endpoint (or with a legacy box's own service):

```bash
curl -X POST http://127.0.0.1:9010/compliance/tls/assess \
  -H "Content-Type: application/json" \
  -d '{"host": "example.com", "port": 443}'
```

The verdict reports the negotiated protocol, cipher, certificate expiry,
whether the chain validates against an up-to-date CA bundle (`certifi`), and
which obsolete protocol versions the server still accepts. `grade` is one of
`modern` / `acceptable` / `legacy` / `insecure` / `unreachable`.

**Modernize** an endpoint the legacy box can't upgrade in place. Start a
TLS-modernizing bridge: the legacy client connects in plaintext (or with its
old TLS) to a local listener, and Bridge re-originates the connection to the
real upstream over TLS 1.2+ with modern roots — like `stunnel` in client mode,
managed via the API.

```bash
# Legacy box points its traffic at 127.0.0.1:<listen_port>; Bridge speaks
# modern TLS to api.example.com:443 on its behalf.
curl -X POST http://127.0.0.1:9010/compliance/tls/bridge \
  -H "Content-Type: application/json" \
  -d '{"upstream_host": "api.example.com", "upstream_port": 443, "listen_port": 8443}'

curl http://127.0.0.1:9010/compliance/tls/bridges        # list
curl -X DELETE http://127.0.0.1:9010/compliance/tls/bridge/<id>   # stop
```

Pass `"listen_port": 0` to get an ephemeral port (returned in the response).
Use `"verify": false` only for self-signed upstreams in testing.

### 2. Drivers / shims

```bash
curl http://127.0.0.1:9010/compliance/drivers | python3 -m json.tool
```

Inventories PCI/USB devices straight from sysfs (no extra deps), reports
whether a kernel driver is bound, and flags **missing drivers** for critical
device classes (network, storage, display, wireless). It enriches matches from
a built-in vendor catalog plus the optional legacy
`automatic driver detection/driver_compatibility.db`. Recommended hardware
**shims** come from the same catalog Bridge uses for execution remediation
(`hardware/shims.py`).

### 3. Web3

Legacy machines also can't reach the decentralized web: EVM JSON-RPC providers
are HTTPS-only with modern TLS, and dApps reference content with `ipfs://`
URIs an old browser can't open.

**Assess** an RPC endpoint (read-only `eth_chainId` / `web3_clientVersion`,
plus the endpoint's TLS posture):

```bash
curl -X POST http://127.0.0.1:9010/compliance/web3/assess \
  -H "Content-Type: application/json" \
  -d '{"rpc_url": "https://cloudflare-eth.com"}'
# -> web3_ready, chain {id, name, currency}, client_version, latency, TLS verdict
```

If the endpoint's TLS isn't modern, the verdict recommends fronting it with the
TLS-modernizing bridge above — so a legacy wallet/client reaches today's RPC
providers over modern TLS.

**Resolve IPFS** content to a gateway URL a legacy browser can fetch:

```bash
curl -X POST http://127.0.0.1:9010/compliance/web3/ipfs-url \
  -H "Content-Type: application/json" \
  -d '{"uri": "ipfs://QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG"}'
# -> {"url": "https://ipfs.io/ipfs/Qm...", "valid_cid": true}
```

`GET /compliance/web3/chains` returns the known chain-id registry. The module is
dependency-free (stdlib `urllib`/`json`) and read-only — it never signs or
sends transactions.

### 4. More modernization helpers

A few smaller but high-impact tools for dragging a legacy box up to today's
baseline:

- **Clock / time** — a wrong system clock is the #1 silent cause of TLS failures
  on old machines (certs look "not yet valid"/"expired"). `POST
  /compliance/time/check` measures skew against NTP and flags it when it's large
  enough to break certificate validation.

  ```bash
  curl -X POST http://127.0.0.1:9010/compliance/time/check \
    -H "Content-Type: application/json" -d '{"ntp_server": "pool.ntp.org"}'
  ```

- **Modern CA bundle** — legacy trust stores ship stale roots. Pull Alma's
  current bundle and install it on the legacy box:

  ```bash
  curl -o alma-ca-bundle.pem http://127.0.0.1:9010/compliance/tls/ca-bundle
  ```

- **Insecure services** — scan a host for plaintext/obsolete services (telnet,
  FTP, bare HTTP, SMBv1, SNMPv1/2c, r-services, plaintext mail/DB) and get a
  modern replacement for each:

  ```bash
  curl -X POST http://127.0.0.1:9010/compliance/services/scan \
    -H "Content-Type: application/json" -d '{"host": "192.168.1.50"}'
  ```

- **DNS-over-HTTPS** — resolve names over encrypted DNS on a legacy box's
  behalf (the building block for a local DoH forwarder):

  ```bash
  curl -X POST http://127.0.0.1:9010/compliance/dns/resolve \
    -H "Content-Type: application/json" \
    -d '{"name": "example.com", "record_type": "A", "provider": "cloudflare"}'
  ```

### Unified report

`POST /compliance/scan` rolls TLS posture, web3 readiness, clock skew, optional
insecure-service scans, the driver inventory, and recommended shims into one
verdict with a prioritized remediation list:

```bash
curl -X POST http://127.0.0.1:9010/compliance/scan \
  -H "Content-Type: application/json" \
  -d '{
    "targets": ["example.com", "api.example.com:8443"],
    "web3_rpc": ["https://cloudflare-eth.com"],
    "scan_services": true
  }'
```

See [`docs/compliance-test-report.md`](docs/compliance-test-report.md) for the
test surface and the bugs found/fixed during testing.

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ALMA_BRIDGE_COMPLIANCE_CA_FILE` | `certifi` bundle | CA bundle for TLS verification + bridge upstreams |
| `ALMA_BRIDGE_COMPLIANCE_TLS_TIMEOUT` | `6.0` | TLS probe timeout (seconds) |
| `ALMA_BRIDGE_COMPLIANCE_SYS_ROOT` | `/sys` | sysfs root for device inventory |
| `ALMA_BRIDGE_COMPLIANCE_DRIVER_CATALOG_DB` | `../automatic driver detection/driver_compatibility.db` | Optional SQLite driver catalog |
| `ALMA_BRIDGE_COMPLIANCE_BRIDGE_LISTEN_HOST` | `127.0.0.1` | Default bind host for TLS bridges |
| `ALMA_BRIDGE_COMPLIANCE_MAX_WORKERS` | `0` (auto) | Probe concurrency. `0` auto-tunes from CPU (capped at 16) |
| `ALMA_BRIDGE_COMPLIANCE_CACHE_TTL` | `60.0` | Seconds to memoize TLS/web3/DoH probes (`0` disables) |
| `ALMA_BRIDGE_AUTOMATION_WEBHOOK_URLS` | `` | Comma-separated webhook URLs for automation lifecycle events |

### Performance / running on low-end hardware

The compliance suite is built to run on a "potato" (single slow core, little
RAM, slow disk/network):

- **Bounded I/O concurrency.** Every independent probe in a scan — each TLS
  target, web3 RPC, service-port check, the NTP query, and the driver
  inventory — runs in one shared, capped thread pool. Since the work is
  network-bound, wall-clock time collapses from *sum of round-trips* to
  *slowest round-trip*, even on one core. Measured ~3.8× faster than sequential
  on a 4-target scan; the gap widens with more targets / slower links.
- **Parallel legacy-TLS probing.** The three obsolete-protocol handshakes per
  host run concurrently instead of one-after-another.
- **Parallel port scans.** An unreachable host costs ~one timeout instead of
  one timeout *per port*.
- **TTL cache.** Repeated or overlapping probes (e.g. a host that's both a TLS
  target and a web3 RPC host) are computed once. Expensive TLS handshakes are
  cached for `CACHE_TTL` seconds, so repeat scans skip the crypto.
- **Tiny footprint.** Worker count is capped (default ≤ 16, auto-tuned from CPU)
  to keep memory low; the modules are pure stdlib + `certifi` with no heavy
  imports.

Tuning knobs: lower `COMPLIANCE_MAX_WORKERS` (e.g. `4`) on very small boxes,
raise `COMPLIANCE_CACHE_TTL` for dashboards that poll often, and skip work you
don't need per request (`check_time`, `scan_services`, `include_drivers`,
`probe_legacy`).

`COMPLIANCE_MAX_WORKERS` is also a **hard global cap on concurrent network
operations**: a single bounded semaphore wraps every socket/handshake/HTTP probe
across the whole process, so even many overlapping heavy scans can never exhaust
file descriptors or CPU. Nested fan-outs (e.g. legacy-TLS probes inside a unified
scan) automatically shrink their worker budget so threads stay bounded to one
fan-out level instead of multiplying (`outer × inner`).

### Self-healing autopilot (the "AI")

When something fails — a legacy launch, a TLS/driver/web3 finding, or any error
string — the autopilot turns it into an actionable, learning-driven plan:

1. **Diagnose.** Transparent signature matching classifies the error
   (`missing_shared_library`, `glibc_too_old`, `arch_32bit`,
   `tls_obsolete_protocol`, `tls_cert_untrusted`, `clock_skew`, `dns_failure`,
   `driver_missing`, `web3_unreachable`, …) with evidence and a confidence score.
2. **Plan pathways.** Each diagnosis maps to ordered remediation *pathways* —
   concrete, copy-pasteable, **distro-aware** steps (apt/dnf/pacman/zypper/apk
   auto-detected from `/etc/os-release`). Steps are tagged `diagnostic`
   (read-only) vs `remediation` (mutating) and whether they need root.
3. **Synthesize new pathways.** For unseen problems (e.g. a never-seen missing
   `.so`), the autopilot builds a bespoke install/relink pathway targeting the
   exact library it extracted from the error.
4. **Learn.** `POST /compliance/autopilot/feedback` records which pathway worked
   for which signature; a Laplace-smoothed online learner re-ranks pathways so
   what actually fixes *this* host floats to the top over time.

```bash
# Diagnose + plan (dry-run; nothing on the host is changed)
curl -X POST http://127.0.0.1:9010/compliance/autopilot/run \
  -H 'content-type: application/json' \
  -d '{"error_text":"libssl.so.1.0.0: cannot open shared object file","execute":false}'

# Let the autopilot run only the *read-only* diagnostic probes
curl -X POST http://127.0.0.1:9010/compliance/autopilot/run \
  -H 'content-type: application/json' \
  -d '{"error_text":"version `GLIBC_2.34'\'' not found","binary":"/opt/app/bin","execute":true}'

# Teach it what worked
curl -X POST http://127.0.0.1:9010/compliance/autopilot/feedback \
  -H 'content-type: application/json' \
  -d '{"signature":"tls_obsolete_protocol","pathway_id":"tls_enable_modern_openssl","success":true}'
```

**Safety:** the autopilot is dry-run by default and **never silently mutates the
host**. With `execute:true` it runs *only* allow-listed read-only probes (`ldd`,
`ldconfig -p`, `test -e`, `ldd --version`, local `curl`…); every mutating step is
returned as a plan for you to review. Destructive commands are never generated.

### 32-bit legacy systems

```bash
# Is this host able to run 32-bit binaries?
curl http://127.0.0.1:9010/compliance/legacy32

# Exact steps to make it 32-bit ready (distro-aware)
curl -X POST http://127.0.0.1:9010/compliance/legacy32/plan -d '{}'
```

`GET /compliance/legacy32` inspects CPU/OS bitness, the 32-bit ELF loader
(`ld-linux.so.2`), multiarch state, core i386 runtime libs, and translation
fallbacks (qemu-user, box86, 32-bit Wine). `POST /compliance/legacy32/plan`
emits the ordered commands to close the gaps:

- **x86-64 host:** enable multiarch + install the i386 runtime → runs 32-bit ELF
  binaries directly.
- **Native 32-bit host:** already runs them; the plan focuses on *modern
  connectivity* (TLS bridge + current CA bundle + DoH).
- **arm64 / non-x86 host:** install qemu-user / box86 to translate x86 binaries.

Either way the plan finishes by pointing the legacy app at Alma's TLS-modernizing
bridge and current CA bundle, so a 32-bit box from a decade ago can still reach
today's TLS-1.3-only, modern-CA web and Web3 endpoints.

### Automation platform (unified spine)

The automation layer ties host modernization, compliance, Bridge execution, and
learning into one auditable pipeline:

**scan → assess → playbook → apply → verify → bridge → autopilot → learn**

| Endpoint | Description |
|----------|-------------|
| `GET /automation/health` | Machine health dashboard (verdict, gaps, recent sessions) |
| `GET /automation/playbooks` | Built-in playbook recipes |
| `POST /automation/run` | Full pipeline (plan-only by default; set `apply: true` to mutate) |
| `POST /automation/approve` | One-time approval token for gated apply |
| `GET /automation/sessions` | Recent automation audit sessions |
| `GET /automation/sessions/{id}` | Session detail with phase timeline |
| `POST /automation/agent/register` | Fleet agent registration |
| `POST /automation/agent/heartbeat` | Agent heartbeat + health snapshot |
| `POST /automation/agent/run` | Run automation as a registered fleet agent |
| `GET /automation/playbooks/{recipe_id}` | Recipe preview (steps + apply_step_ids) |

**K-12 deployment:** see [`docs/k12-lab-deployment.md`](../docs/k12-lab-deployment.md) (topology, Windows GPO/PDQ, pilot checklist).

**Production:** set `ALMA_BRIDGE_API_KEY` to protect apply/run endpoints — see [`SECURITY.md`](SECURITY.md).

```bash
# Plan-only run (assess + playbook, no sudo)
curl -X POST http://127.0.0.1:9010/automation/run \
  -H 'content-type: application/json' \
  -d '{"apply": false}'

# Apply with approval token (one-time gate)
TOKEN=$(curl -s -X POST http://127.0.0.1:9010/automation/approve \
  -H 'content-type: application/json' \
  -d '{"step_ids":["clock_sync","install_ca_bundle"]}' | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

curl -X POST http://127.0.0.1:9010/automation/run \
  -H 'content-type: application/json' \
  -d "{\"apply\": true, \"approval_token\": \"$TOKEN\", \"playbook_recipe\": \"school-lab\"}"

# Fleet agent CLI (on remote machines)
python scripts/alma-agent.py register
python scripts/alma-agent.py --agent-id <id> heartbeat
python scripts/alma-agent.py --agent-id <id> run --recipe potato-browser-only --apply --allow-mutations
```

Built-in playbook recipes: `school-lab` (classroom web labs), `container-lab` (VM-like
container shim isolation), `potato-browser-only`, `full-legacy-x86`, `connectivity-only`.
Post-apply verification re-assesses the host, diffs gaps,
and probes HTTPS. Sessions are stored in SQLite alongside Bridge outcomes.

Set `ALMA_BRIDGE_AUTOMATION_WEBHOOK_URLS` (comma-separated) to receive
`automation.completed` webhook events.

The React UI exposes this under **Modernization → Automation** tab at
`http://localhost:3001/app/compliance`.

### Container Shim Pack (VM-like isolation)

When a school lab PC cannot be upgraded at all, run legacy binaries inside Alma's
**sandbox container** instead of on the host. Alma bundles Wine/QEMU userland with
the full **shim catalog** (GPU, memory caps, host networking for TLS bridges):

| Endpoint | Description |
|----------|-------------|
| `GET /execution/sandbox/status` | Docker/Podman + sandbox image readiness |
| `GET /container/shims` | Shim catalog + recommended shims for this host |
| `POST /container/shim-pack` | Plan a container run (command + env + docker preview) |
| `POST /container/run` | Execute the shim pack |

```bash
# Build sandbox image once
cd alma-bridge && docker build -t alma-bridge-sandbox:latest .

# Plan
curl -X POST http://127.0.0.1:9010/container/shim-pack \
  -H 'content-type: application/json' \
  -d '{"file_path":"/path/to/legacy.exe"}'

# Run (Wine/QEMU + shims inside container)
curl -X POST http://127.0.0.1:9010/container/run \
  -H 'content-type: application/json' \
  -d '{"file_path":"/path/to/legacy.exe","use_sudo":true}'

# Automation recipe (plan + optional run)
curl -X POST http://127.0.0.1:9010/automation/run \
  -H 'content-type: application/json' \
  -d '{"playbook_recipe":"container-lab","file_path":"/path/to/binary","container_run":true}'
```

UI: **Modernization → Container lab** tab.

## Roadmap

- [x] Adapters to import almasysdet + alma_resolve history
- [x] ASOD hardware detection integration for hardware shims
- [x] Trained strategy ranker (gradient boosting on outcome DB)
- [x] Legacy compliance: TLS posture + modernizing bridge + driver/shim inventory
- [x] Web3 compliance: JSON-RPC readiness, chain registry, IPFS URL resolution
- [x] Modernization helpers: clock/NTP skew, CA bundle, insecure-service scan, DoH
- [x] Self-healing autopilot: diagnose → ranked pathways + online feedback learning
- [x] Dependency-rebuild planner (distro-aware, dry-run, synthesized pathways)
- [x] 32-bit legacy readiness assessor + enablement planner
- [x] Global concurrency cap + nesting-aware worker budget (heavy-load safe)
- [x] Automation platform: unified run, verify-after-apply, approval tokens, fleet agent
- [x] Host modernization: assess → playbook → apply (browser, CA, multiarch, potato tuning)
- [x] Container Shim Pack: VM-like sandbox runs with full Alma shim catalog
- [ ] LLM-assisted remediation for novel error signatures
- [ ] Proton version search across compatibility tools
- [ ] Auto-provision missing drivers from a trusted remote catalog
