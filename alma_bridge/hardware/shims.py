from __future__ import annotations

from typing import Any, Dict, List


# Hardware and runtime shims Alma can apply when bridging legacy software to modern hosts.
SHIM_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "software_opengl",
        "category": "gpu",
        "description": "Force software OpenGL rendering for legacy GPU/driver combos.",
        "env": {
            "LIBGL_ALWAYS_SOFTWARE": "1",
            "MESA_LOADER_DRIVER_OVERRIDE": "llvmpipe",
        },
        "applies_when": ["legacy_or_generic_gpu_driver", "gpu_crash", "missing_opengl"],
    },
    {
        "id": "disable_dxvk",
        "category": "gpu",
        "description": "Disable DXVK and fall back to WineD3D.",
        "env": {
            "DXVK_DISABLE": "1",
            "WINE_D3D_RENDERER": "gdi",
        },
        "applies_when": ["dxvk_failure", "vulkan_missing", "legacy_or_generic_gpu_driver"],
    },
    {
        "id": "virtual_desktop",
        "category": "display",
        "description": "Run inside a Wine virtual desktop to avoid fullscreen issues.",
        "env": {
            "ALMA_WINE_VIRTUAL_DESKTOP": "1024x768",
        },
        "applies_when": ["display_crash", "fullscreen_failure"],
    },
    {
        "id": "win32_prefix",
        "category": "architecture",
        "description": "Use a 32-bit Wine prefix for legacy Windows binaries.",
        "env": {
            "WINEARCH": "win32",
        },
        "applies_when": ["architecture_mismatch", "32bit_cpu"],
    },
    {
        "id": "pulse_audio_compat",
        "category": "audio",
        "description": "Route audio through PulseAudio compatibility layer.",
        "env": {
            "PULSE_LATENCY_MSEC": "60",
        },
        "applies_when": ["audio_failure"],
    },
    {
        "id": "old_cpu_compat",
        "category": "cpu",
        "description": "Reduce thread pressure for very old or low-core CPUs.",
        "env": {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
        },
        "applies_when": ["low_memory", "32bit_cpu"],
    },
    {
        "id": "ld_library_path_32",
        "category": "native",
        "description": "Expose 32-bit system libraries for legacy native ELF binaries.",
        "env": {
            "LD_LIBRARY_PATH": "/usr/lib/i386-linux-gnu:/lib/i386-linux-gnu",
        },
        "applies_when": ["missing_dependency", "no_multiarch_libs"],
    },
    {
        "id": "qemu_cpu_compat",
        "category": "emulation",
        "description": "Use conservative CPU model when emulating foreign architectures.",
        "env": {
            "QEMU_CPU": "max",
        },
        "applies_when": ["architecture_mismatch"],
    },
    {
        "id": "hdd_io_compat",
        "category": "storage",
        "description": "Reduce IO pressure on rotational storage during legacy app launches.",
        "env": {
            "ALMA_IO_NICE": "1",
        },
        "applies_when": ["rotational_storage"],
    },
    {
        "id": "swappiness_tuning",
        "category": "memory",
        "description": "Hint launchers to avoid aggressive memory allocation on swap-heavy hosts.",
        "env": {
            "MALLOC_ARENA_MAX": "2",
        },
        "applies_when": ["high_swappiness", "low_memory"],
    },
    {
        "id": "mesa_glthread_off",
        "category": "gpu",
        "description": "Disable Mesa GL threading for older integrated GPUs.",
        "env": {
            "mesa_glthread": "false",
        },
        "applies_when": ["legacy_or_generic_gpu_driver", "unknown_gpu"],
    },
    {
        "id": "electron_disable_gpu",
        "category": "gpu",
        "description": "Disable Electron's GPU process under Wine (--disable-gpu). Every Chromium GPU backend fails the 'shared context for virtualization' and crash-loops on Wine, so this is the only stable option.",
        "env": {
            "ALMA_ELECTRON_ARGS": "--disable-gpu --no-sandbox",
        },
        "applies_when": ["electron_gpu_crash", "electron_app"],
    },
    # Back-compat: the old id mapped to the (wrong) ANGLE flags; keep the id but
    # point it at the correct --disable-gpu behavior.
    {
        "id": "electron_software_gl",
        "category": "gpu",
        "description": "Alias of electron_disable_gpu (the only stable Electron-under-Wine GPU config).",
        "env": {
            "ALMA_ELECTRON_ARGS": "--disable-gpu --no-sandbox",
        },
        "applies_when": ["electron_gpu_crash", "electron_app"],
    },
    {
        "id": "electron_elevate_passthrough",
        "category": "compat",
        "description": "Install a CreateProcess passthrough over electron-builder's elevate.exe so 'runas' UAC elevation (unsupported by Wine) no longer kills elevated child processes.",
        "env": {
            "ALMA_INSTALL_ELEVATE_PASSTHROUGH": "1",
        },
        "applies_when": ["elevation_failed", "electron_app"],
    },
    {
        "id": "electron_launcher_guard_workaround",
        "category": "compat",
        "description": "Wrap the app's elevated sidecar so its launcher_guard watches a correctly-named, reliably-alive decoy (works around Wine misreporting the live launcher PID as exited).",
        "env": {
            "ALMA_INSTALL_CS_GUARD_WORKAROUND": "1",
        },
        "applies_when": ["launcher_guard_shutdown"],
    },
    {
        "id": "container_legacy_net",
        "category": "container",
        "description": "Use host networking in the sandbox so legacy apps reach local TLS bridges and district proxies.",
        "env": {
            "ALMA_CONTAINER_NETWORK": "host",
        },
        "applies_when": ["tls_obsolete_protocol", "dns_failure"],
    },
    {
        "id": "container_memory_cap",
        "category": "container",
        "description": "Cap container RAM so one legacy app cannot exhaust a shared lab machine.",
        "env": {
            "ALMA_CONTAINER_MEMORY": "768m",
        },
        "applies_when": ["low_memory", "high_swappiness"],
    },
    {
        "id": "container_cpu_cap",
        "category": "container",
        "description": "Limit container CPU on very old lab hardware.",
        "env": {
            "ALMA_CONTAINER_CPUS": "1.0",
        },
        "applies_when": ["32bit_cpu", "low_memory"],
    },
]


def recommended_shims_from_profile(hardware_profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    indicators = list(hardware_profile.get("legacy_indicators", []))
    asod = hardware_profile.get("asod", {})
    indicators.extend(asod.get("legacy_indicators", []))
    return shims_for_indicators(list(dict.fromkeys(indicators)))


def shims_for_indicators(indicators: List[str], error_signature: str | None = None) -> List[Dict[str, Any]]:
    keys = set(indicators)
    if error_signature:
        keys.add(error_signature)

    matched = []
    for shim in SHIM_CATALOG:
        triggers = set(shim.get("applies_when", []))
        if keys & triggers:
            matched.append(shim)
    return matched


def shim_env(shim_ids: List[str]) -> Dict[str, str]:
    env: Dict[str, str] = {}
    catalog = {item["id"]: item for item in SHIM_CATALOG}
    for shim_id in shim_ids:
        shim = catalog.get(shim_id)
        if shim:
            env.update(shim.get("env", {}))
    return env
