# Native Alma Runtime — Threat Model (Milestone 1)

## Scope

Milestone 1 executes **allow-listed console PE fixtures** inside an **isolated
worker subprocess**. The FastAPI/Uvicorn process never maps or executes PE
images directly.

## Assets

- Host filesystem outside the sandbox workspace
- Bridge session state and verification authority (ADR-001)
- Operator credentials and API keys
- Other tenant workloads on shared hosts

## Trust boundaries

```
FastAPI (untrusted PE metadata only)
    │  spawn + IPC (JSON)
    ▼
Worker subprocess (PE map + shim dispatch)
    │  allow-listed kernel32 imports only
    ▼
Sandbox workspace (temp dir, fixture I/O only)
```

## Threats and mitigations

| Threat | Mitigation |
|--------|------------|
| Arbitrary code execution in API process | Worker subprocess only; provider never maps PE in Uvicorn |
| Import of malicious DLLs / syscalls | Strict import allow-list (`kernel32.dll`); eligibility rejects TLS, delay-load, GUI, COM, .NET |
| Path traversal via Win32 APIs | `filesystem/paths.py` resolves paths under workspace root only |
| Resource exhaustion | Execution timeout; bounded stdout/stderr capture |
| PE32 on 64-bit host without 32-bit worker | Fail-closed with explicit reason code |
| Bypass of VerificationEngine | Runtime providers cannot import `VerificationGateway`; success remains orchestrator-owned |
| Experimental flag misuse | `native_runtime_enabled` and `allow_experimental_runtimes` both required |

## Out of scope (M1)

- GUI subsystem PE, installers, Electron
- Network sockets, registry mutation, process creation
- Production orchestrator auto-selection without explicit flags

## Residual risk

Minimal console PE that passes eligibility may still contain bug-triggering
machine code within the mapped image. Subprocess isolation limits blast radius
but does not provide full VM isolation. Container provider remains the stronger
isolation boundary for untrusted binaries.
