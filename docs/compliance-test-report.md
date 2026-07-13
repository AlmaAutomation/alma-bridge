# Alma Bridge — Legacy Compliance Test Report

Covers the `alma_bridge/compliance/` capability (TLS/HTTPS, drivers/shims,
web3). Documents the test surface, every bug found during vigorous testing,
and the mitigation/fix applied.

## Test surface

| Suite | File | What it covers |
|-------|------|----------------|
| TLS verdict logic | `tests/test_compliance_tls.py` | Pure `evaluate_tls_posture` across modern/legacy/expired/self-signed/weak-cipher/handshake-failed cases |
| Drivers | `tests/test_compliance_drivers.py` | sysfs parsing + catalog classification against a fake `/sys` tree |
| Report | `tests/test_compliance_report.py` | `parse_target` (incl. IPv6) + unified report assembly |
| TLS bridge | `tests/test_compliance_bridge.py` | Lifecycle + **live plaintext→TLS round-trip** with an ephemeral openssl cert |
| Web3 | `tests/test_compliance_web3.py` | JSON-RPC parsing, chain registry, CID validation, IPFS URL rewriting, readiness verdict |
| API | `tests/test_compliance_api.py` | All `/compliance/*` routes via FastAPI `TestClient` (no external network) |
| Edge cases | `tests/test_compliance_edgecases.py` | Fuzz/adversarial inputs + regression tests for the bugs below |
| Modernization | `tests/test_compliance_modernization.py` | Clock-skew verdict, insecure-service registry/probe, DoH JSON parsing |
| Performance | `tests/test_compliance_perf.py` | TTL cache hit/expiry, worker tuning/caps, concurrent order + parallelism |
| **Stress / heavy** | `tests/test_compliance_stress.py` | Cache races (40 threads), nested-fan-out thread bounding, bridge under **100 concurrent connections** (FD-leak check), 40× repeated reports (thread/FD-leak check) |
| **Autopilot** | `tests/test_compliance_autopilot.py` | Diagnosis signatures, package-manager detection, pathway planning/synthesis, online re-ranking, safe-diagnostic gating |
| **32-bit** | `tests/test_compliance_legacy32.py` | Readiness across x86-64/native-32/arm64, distro-aware enablement plans |

**Result:** all compliance tests pass; full Bridge suite green (277 tests).

## Performance (low-end hardware)

The suite is optimized to run on a single slow core with little RAM:

- All independent probes in a scan run in one **bounded** thread pool
  (`_perf.resolve_workers`, capped at 16, auto-tuned from CPU). I/O-bound work
  → wall time is the slowest probe, not the sum. Measured **~3.8× faster** than
  sequential on a 4-target scan.
- Legacy-TLS handshakes and service-port checks are parallelized.
- A thread-safe **TTL cache** (`_perf.TTLCache`) memoizes TLS/web3/DoH probes so
  repeated/overlapping scans skip the crypto; the driver catalog is cached by
  path+mtime.
- Tunable via `ALMA_BRIDGE_COMPLIANCE_MAX_WORKERS` and
  `ALMA_BRIDGE_COMPLIANCE_CACHE_TTL`.

## Modernization helpers (added after first pass)

- **Clock/time** (`compliance/timecheck.py`) — NTP probe + pure skew verdict.
  Large skew is flagged because it breaks TLS cert validation. Validated live:
  skew ~0.9s against `pool.ntp.org` → compliant.
- **CA bundle** (`GET /compliance/tls/ca-bundle`) — serves the current certifi
  PEM for legacy trust stores.
- **Insecure services** (`compliance/services.py`) — TCP-probes a host for
  telnet/FTP/HTTP/SMBv1/SNMP/r-services/plaintext mail+DB and recommends modern
  replacements.
- **DNS-over-HTTPS** (`compliance/dns.py`) — resolves names over DoH
  (Cloudflare/Google/Quad9). Validated live: A/AAAA resolution + NXDOMAIN
  handling on both providers.

All four follow the pure-logic/live-I/O split and are folded into
`POST /compliance/scan` (clock always; services opt-in via `scan_services`).

### Live validation (real endpoints)

Run manually (needs outbound network) — not part of CI:

- TLS: `example.com` → `modern`; `expired.badssl.com` / `self-signed.badssl.com`
  → flagged untrusted; `tls-v1-0/1-1.badssl.com` → `legacy` (reachable).
- Web3: `cloudflare-eth.com` & `ethereum-rpc.publicnode.com` → ready, chain id 1
  (Ethereum Mainnet), client version captured; `polygon-rpc.com` → not ready
  (HTTP 401, correctly reported).
- Bridge: a plaintext HTTP/1.1 client through the bridge to `example.com:443`
  returned `HTTP/1.1 200 OK` over modern TLS (verify on).

## Bugs found & fixed

### BUG #1 — `ssl.TLSVersion.TLSv1` DeprecationWarning on every probe
- **Severity:** medium (log spam now; hard error in a future Python).
- **Symptom:** Each TLS probe emitted `DeprecationWarning: ssl.TLSVersion.TLSv1
  is deprecated` because we intentionally lower `minimum_version` to probe
  legacy hosts.
- **Fix:** Centralized all legacy `minimum_version`/`maximum_version`
  assignments in `_set_min_version()`, which suppresses the *intentional*
  `DeprecationWarning` and returns `False` if the local OpenSSL refuses the
  version. (`compliance/tls.py`)
- **Regression test:** `test_assess_unreachable_emits_no_deprecation_warning`
  (runs the probe under `warnings.simplefilter("error", DeprecationWarning)`).

### BUG #2 — `parse_target` crashed on IPv6 literals
- **Severity:** medium (500 error on valid input like `[::1]:8443`).
- **Symptom:** Naive `partition(":")` split IPv6 addresses incorrectly and
  `int(port)` raised `ValueError`.
- **Fix:** Handle bracketed IPv6 (`[host]` / `[host]:port`) explicitly and use
  `rpartition(":")` for host:port otherwise. (`compliance/report.py`)
- **Regression test:** `test_parse_target_ipv6` (4 cases incl. `https://` URLs).

### BUG #3 — Reachable legacy-TLS-only hosts misreported as `unreachable`
- **Severity:** high (defeats the core use case — detecting legacy endpoints).
- **Symptom:** A host that is up but only speaks TLS 1.0/1.1 (which modern
  OpenSSL refuses) failed both handshakes, so it was graded `unreachable`
  instead of `legacy`. Confirmed live against `tls-v1-1.badssl.com:1011`.
- **Fix:** On handshake failure, fall back to a plain TCP connectivity probe
  (`_tcp_reachable`). If TCP connects, mark `reachable=True` +
  `tls_handshake_failed=True`; `evaluate_tls_posture` grades these `legacy`
  with the "front it with a TLS-modernizing bridge" recommendation.
  (`compliance/tls.py`)
- **Regression test:** `test_legacy_only_server_reachable_but_handshake_failed`.

### BUG #4 — Misleading "certificate not trusted" blocker on handshake failure
- **Severity:** low (cosmetic / accuracy).
- **Symptom:** When the TLS handshake never completed, we still emitted a
  "certificate chain not trusted" blocker, even though no certificate was ever
  evaluated — the real issue is the protocol.
- **Fix:** Suppress the cert-trust blocker when `tls_handshake_failed` is set;
  the protocol blocker already explains the failure. (`compliance/tls.py`)

## Heavy / recursive stress pass — bugs found & fixed

A second, harder pass added `tests/test_compliance_stress.py` (cache races,
nested fan-outs, the bridge under 100 concurrent connections, and 40× repeated
reports) to hunt for leaks and thread storms under load.

### BUG #5 — Nested concurrency caused a thread explosion
- **Severity:** high (OOM / FD exhaustion risk on low-end hosts — the opposite
  of the "runs on a potato" goal).
- **Symptom:** A unified scan fans out across jobs *and* each job fanned out
  again (legacy-TLS probes, service ports). With independent transient pools the
  thread count multiplied `outer × inner`; the stress test measured **102 live
  threads** from a 30×10 nested fan-out.
- **Fix (`compliance/_perf.py`):**
  1. **Nesting-aware worker budget** — a `threading.local` flag marks code
     running inside a worker; nested `map_concurrent`/`run_jobs` shrink to
     `NESTED_WORKER_CAP` (4), so total threads stay at one fan-out level.
  2. **Global network-concurrency semaphore** — a single `BoundedSemaphore`
     (`network_slot()`, sized from `COMPLIANCE_MAX_WORKERS`) wraps *every* leaf
     socket/handshake/HTTP/NTP op across the process. Only leaf I/O holds a
     slot (never orchestration), so nesting can throttle but never deadlock.
  3. The unified report now runs jobs through `run_jobs` so the flag propagates.
- **Result:** same 30×10 fan-out now peaks well under the bound; verified by
  `test_map_concurrent_recursive_no_thread_explosion`.

### BUG #6 — `dd` denylist token falsely matched `ldd`
- **Severity:** medium (the autopilot's safe-diagnostic gate rejected the very
  read-only probes it's supposed to auto-run, e.g. `ldd --version`).
- **Symptom:** The substring denylist for mutating commands matched `"dd "`
  inside `"ldd "`, so legitimate diagnostics were blocked.
- **Fix:** Switched the gate to **word-boundary regex** (`\bdd\b`, `\brm\b`,
  package-manager names, redirections). (`compliance/autopilot.py`)
- **Regression test:** `test_is_safe_diagnostic_rejects_mutations`.

### BUG #7 — arm64 misclassified as able to run x86-32 via multiarch
- **Severity:** medium (wrong 32-bit enablement plan on ARM servers/Pi).
- **Symptom:** `aarch64` was bucketed with `x86_64`, so the planner suggested
  `dpkg --add-architecture i386` instead of an x86 translation layer.
- **Fix:** Distinguish `is_x86_64` (multiarch path) from other 64-bit hosts
  (qemu-user/box86 translation path). (`compliance/legacy32.py`)
- **Regression test:** `test_assess_arm_needs_translation`.

No FD or thread leaks were found in the bridge-under-load or repeated-report
tests (FD count and `threading.active_count()` return to baseline).

## Self-healing autopilot

`compliance/autopilot.py` + `compliance/learning.py` add an adaptive remediation
engine (not an LLM — a transparent, learning expert system):

- **Diagnose** free-text errors into signatures with evidence + confidence.
- **Plan** ranked, distro-aware remediation *pathways* (apt/dnf/pacman/zypper/apk
  auto-detected); steps tagged diagnostic vs mutating + root requirement.
- **Synthesize** bespoke pathways for unseen problems (e.g. a specific missing
  `.so` → targeted install/relink).
- **Learn** from `record_outcome(signature, pathway_id, success)` — a
  Laplace-smoothed online score re-ranks pathways toward what works on this host
  (`test_feedback_reranks_pathways` proves a lower-priority pathway overtakes the
  default after repeated successes).
- **Safety:** dry-run by default; `execute=true` runs only an allow-listed set of
  read-only probes; mutating steps are never auto-run and destructive commands
  are never generated.

## 32-bit legacy readiness

`compliance/legacy32.py` assesses whether a host can run 32-bit binaries (CPU/OS
bitness, ELF32 loader, multiarch, core i386 libs, qemu/box86/Wine fallbacks) and
emits distro-aware enablement steps. Native 32-bit hosts are steered toward
modern *connectivity* (TLS bridge + CA bundle + DoH) so decade-old boxes still
reach today's TLS-1.3/modern-CA web and Web3 endpoints.

## Known limitations / hardening notes (not bugs)

- **SSRF surface:** `/compliance/web3/assess` and `/compliance/tls/assess` take
  a user-supplied host/URL and connect to it. Scheme is restricted to
  `http(s)`. In a multi-tenant deployment, put these behind an allowlist or
  network egress controls. Bridge binds to `127.0.0.1` by default.
- **TLS bridge & long-lived connections:** the bridge pumps bytes until either
  side closes; idle HTTP keep-alive connections stay open until the client
  closes them. Fine for on-demand use; add idle timeouts if exposing broadly.
- **USB driver flagging:** USB devices are inventoried but not flagged as
  "missing driver" (their class isn't mapped to the critical set). PCI
  network/storage/display/wireless devices are.
- **Driver auto-provisioning** is intentionally not implemented: installing
  binary drivers requires a trust/signing decision (roadmap item).
