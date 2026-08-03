# Runtime Dependency Audit — Phase 0A/0B

Audit of Wine, Proton, and container execution dependencies across Alma Bridge,
conducted to define the Compatibility Runtime Provider boundary (ADR-014).

## Executive summary

Alma Bridge today routes PE and mixed-format binaries through **host Wine**,
**Proton**, and **sandbox container** execution paths. These paths are
scattered across `execution/`, `compatibility/planner.py`, `hardware/`, and
`learning/orchestrator.py`. No single module owns runtime capability
declarations or provider lifecycle.

Phase 0B introduces `alma_bridge/runtime/` as a **contract layer** that wraps
existing execution patterns without changing orchestrator behavior or
VerificationEngine authority.

## Dependency map

| Module | Wine/Proton/Container touchpoints | Role |
|--------|-----------------------------------|------|
| `compatibility/strategies.py` | Strategy IDs `wine_host`, `proton_host`, `container_*` | Declares required host capabilities (`wine`, `proton`, `docker`) |
| `compatibility/planner.py` | Resolves Wine/Proton paths, builds commands | Plan construction; no execution |
| `execution/runner.py` | `execute_attempt`, Wine GUI handoff, container sandbox | Authoritative attempt execution |
| `execution/preflight.py` | `WINEPREFIX`, Windows version checks | Prefix readiness |
| `execution/wine_process.py` | rundll32 probes, process observation | Wine-specific observation |
| `execution/sandbox.py` | `run_in_container` | Container execution |
| `execution/container_command.py` | `wine` inside container image | Container command wrapping |
| `hardware/profiler.py` | Detects Wine/Proton/Docker on host | Capability discovery |
| `hardware/proton.py` | Proton install discovery | Path resolution |
| `hardware/proton_env.py` | Proton environment variables | Launch env |
| `learning/orchestrator.py` | Full bridge loop, remediation, verification gateway | **Must not be imported by runtime providers** |
| `session/verification_gateway.py` | Success authority | **Must not be imported by runtime providers** |

## Import boundary (ADR-014)

Runtime providers **may** import:

- `alma_bridge.hardware.*` (read-only host profiling)
- `alma_bridge.compatibility.strategies` (binary classification, strategy metadata)
- `alma_bridge.execution.container_command` (command building only)
- `alma_bridge.execution.preflight` (readiness checks)

Runtime providers **must not** import:

- `alma_bridge.session.verification_gateway` / `VerificationGateway`
- `alma_bridge.learning.orchestrator` / `BridgeOrchestrator`
- `alma_bridge.session.mutations`
- Any module that transitions session lifecycle or declares verified success

## Strategy → provider mapping (Phase 0B)

| Strategy ID | Runtime provider ID | Notes |
|-----------|---------------------|-------|
| `wine_host` | `wine` | System Wine on host |
| `proton_host` | `proton` | Latest discovered Proton |
| `container_compat` | `container` | Docker/Podman sandbox |
| `container_podman` | `container` | Same provider; podman capability |
| `native_host` | *(none)* | Native ELF; outside runtime layer |
| `native_multiarch` | *(none)* | Native with multiarch libs |
| `qemu_user` | *(none)* | Foreign-arch ELF via qemu-user |

## Capability inventory (host)

From `hardware/profiler.profile_hardware()`:

- `capabilities.wine` — `wine` / `wine64` on PATH
- `capabilities.proton` — Proton compatibility tool discovered
- `capabilities.docker` — Docker daemon reachable
- `capabilities.podman` — Podman available
- `capabilities.multiarch` — 32-bit loader present
- `capabilities.qemu_user` — qemu-user-static available

## Gaps and Phase 0B scope

1. **No unified runtime capability model** — addressed by `RuntimeCapabilities`.
2. **No provider registry** — addressed by deterministic `RuntimeRegistry`.
3. **Planner selects strategies, not providers** — addressed additively via `runtime/planner_bridge.py`.
4. **No conformance baseline comparison** — addressed by `runtime/conformance/`.
5. **Native Alma runtime** — design-only under `native_runtime/`; `NativeAlmaRuntime` is fail-closed experimental.

## Non-goals (Phase 0B)

- Replacing Wine or forking Wine
- Changing orchestrator execution loop
- Moving VerificationEngine authority
- Dynamic untrusted provider loading
