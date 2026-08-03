# Runtime Capability Model

## Capability states

Each provider declares capabilities using one of five states:

| State | Meaning |
|-------|---------|
| `supported` | Provider fully supports the capability on this host |
| `partial` | Supported with limitations or host-specific gaps |
| `unsupported` | Not available; selection should exclude |
| `unknown` | Not yet evaluated (experimental providers) |
| `delegated` | Handled by an underlying layer (e.g. Wine prefix mutations) |

## Canonical capabilities (Phase 0B)

| Key | Description |
|-----|-------------|
| `pe_console` | PE console/subsystem applications |
| `pe_gui` | PE GUI applications |
| `pe_installer` | PE installers (MSI/setup) |
| `pe_electron` | Electron-on-Wine family |
| `elf_native` | Native ELF execution |
| `elf32_multiarch` | 32-bit ELF via multiarch |
| `elf_foreign_qemu` | Foreign-arch ELF via qemu-user |
| `container_isolation` | Sandbox container execution |
| `registry_mutation` | Wine registry changes |
| `dll_override` | DLL override / winetricks-style shims |

## Provider declarations (default host)

| Provider | pe_console | pe_gui | container_isolation | Notes |
|----------|------------|--------|---------------------|-------|
| wine | supported* | supported* | unsupported | *when Wine on PATH |
| proton | supported* | supported | unsupported | Stronger PE GUI |
| container | partial | partial | supported* | Broad format coverage |
| native_alma | unknown | unsupported | unsupported | Fail-closed |

## Selection

`RuntimeRequirements` lists required and preferred capabilities.
`select_providers()` ranks registered providers by fitness without altering
existing strategy IDs.

Strategy → provider mapping:

- `wine_host` → `wine`
- `proton_host` → `proton`
- `container_compat` / `container_podman` → `container`

Native and qemu strategies have no runtime provider mapping.

## Implementation

- Model: `alma_bridge/runtime/capabilities.py`
- Selection: `alma_bridge/runtime/selection.py`
- Requirements: `alma_bridge/runtime/models.py`
