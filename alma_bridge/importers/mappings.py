from __future__ import annotations

from typing import Dict, Optional


SYSDET_RUNTIME_TO_STRATEGY: Dict[str, str] = {
    "wine": "wine_host",
    "proton": "proton_host",
    "native": "native_host",
    "qemu": "qemu_user",
    "qemu-x86_64": "qemu_user",
    "qemu-i386": "qemu_user",
    "docker": "container_compat",
    "podman": "container_podman",
}

SYSDET_DETECTED_ERROR_TO_SIGNATURE: Dict[str, str] = {
    "missing_visual_c_runtime": "missing_visual_c_runtime",
    "nsis_installer_launch_failure": "nsis_installer_failure",
    "wine_loader_failure": "wine_prefix_problem",
    "missing_dll": "missing_dll",
    "architecture_mismatch": "architecture_mismatch",
    "file_not_found": "file_not_found",
}

RESOLVE_ACTION_TO_REMEDIATION: Dict[str, str] = {
    "test_launcher_with_software_rendering": "software_rendering",
    "test_launcher_with_wined3d_fallback": "wined3d_fallback",
    "test_launcher_with_virtual_desktop": "virtual_desktop",
    "run_launcher_with_wine_debug_logs": "wine_debug_collect",
    "test_launcher_with_clean_stdio_and_logging_overrides": "baseline_retry",
    "launch_with_best_known_profile": "baseline_retry",
    "test_launcher_with_gpu_process_disabled": "software_rendering",
    "test_launcher_with_networking_workarounds": "baseline_retry",
    "test_launcher_with_network_stub_profile": "baseline_retry",
}

RESOLVE_SIGNAL_TO_SIGNATURE: Dict[str, str] = {
    "opengl_pixel_format_failure": "gpu_crash",
    "directcomposition_not_implemented": "display_crash",
    "wine_graphics_stack": "gpu_crash",
    "wine_int3_breakpoint": "wine_int3_crash",
    "electron_int3_crash": "wine_int3_crash",
    "missing_dotnet_runtime": "missing_visual_c_runtime",
    "missing_vc_runtime": "missing_visual_c_runtime",
}


def normalize_error_signature(
    signature: Optional[str],
    detected_error: Optional[str] = None,
) -> str:
    if signature and signature not in {"none", "null", ""}:
        return signature
    if detected_error:
        return SYSDET_DETECTED_ERROR_TO_SIGNATURE.get(detected_error, detected_error)
    return "unknown_error"
