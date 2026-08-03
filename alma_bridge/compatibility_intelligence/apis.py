"""Windows API classification registry — maps imports to capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from alma_bridge.compatibility_intelligence.models import (
    ApiComplexity,
    ApiClassificationResult,
    ImplementationStatus,
    ProvenanceEvidence,
)

REGISTRY_VERSION = "aci_api_registry_v1"
REGISTRY_SOURCE = "aci_curated_fixture_registry"


@dataclass(frozen=True)
class ApiEntry:
    dll: str
    function: str
    capability_id: str
    complexity: ApiComplexity
    native_status: ImplementationStatus
    wine_status: ImplementationStatus
    documentation_ref: str = ""


def _k32(
    function: str,
    capability_id: str,
    *,
    complexity: ApiComplexity = ApiComplexity.LOW,
    native: ImplementationStatus = ImplementationStatus.SUPPORTED,
    wine: ImplementationStatus = ImplementationStatus.SUPPORTED,
    doc: str = "",
) -> ApiEntry:
    return ApiEntry("kernel32.dll", function, capability_id, complexity, native, wine, doc)


# Curated registry for kernel32 APIs used by native_runtime test fixtures + shim surface.
_CURATED: Tuple[ApiEntry, ...] = (
    _k32("GetStdHandle", "console.stdout"),
    _k32("WriteFile", "console.stdout"),
    _k32("ReadFile", "filesystem.basic_io"),
    _k32("CreateFileW", "filesystem.basic_io", complexity=ApiComplexity.MEDIUM),
    _k32("CloseHandle", "filesystem.basic_io"),
    _k32("ExitProcess", "process.exit"),
    _k32("GetCommandLineW", "process.arguments"),
    _k32("GetEnvironmentVariableW", "process.environment"),
    _k32("GetLastError", "error.handling"),
    _k32("SetLastError", "error.handling"),
    _k32("GetModuleFileNameW", "process.identity"),
    _k32("GetCurrentProcessId", "process.identity"),
    _k32("Sleep", "process.timing"),
    # Additional common kernel32 APIs (classified, not all native-supported)
    ApiEntry(
        "kernel32.dll",
        "CreateProcessW",
        "process.creation",
        ApiComplexity.MEDIUM,
        ImplementationStatus.UNSUPPORTED,
        ImplementationStatus.SUPPORTED,
    ),
    ApiEntry(
        "kernel32.dll",
        "LoadLibraryW",
        "filesystem.basic_io",
        ApiComplexity.MEDIUM,
        ImplementationStatus.UNSUPPORTED,
        ImplementationStatus.SUPPORTED,
    ),
    ApiEntry(
        "kernel32.dll",
        "GetProcAddress",
        "filesystem.basic_io",
        ApiComplexity.MEDIUM,
        ImplementationStatus.UNSUPPORTED,
        ImplementationStatus.SUPPORTED,
    ),
    # user32
    ApiEntry(
        "user32.dll",
        "CreateWindowExW",
        "gui.windowing",
        ApiComplexity.HIGH,
        ImplementationStatus.UNSUPPORTED,
        ImplementationStatus.SUPPORTED,
    ),
    ApiEntry(
        "user32.dll",
        "MessageBoxW",
        "gui.windowing",
        ApiComplexity.MEDIUM,
        ImplementationStatus.UNSUPPORTED,
        ImplementationStatus.SUPPORTED,
    ),
    ApiEntry(
        "user32.dll",
        "ShowWindow",
        "gui.windowing",
        ApiComplexity.MEDIUM,
        ImplementationStatus.UNSUPPORTED,
        ImplementationStatus.SUPPORTED,
    ),
    # advapi32
    ApiEntry(
        "advapi32.dll",
        "RegOpenKeyExW",
        "registry.read",
        ApiComplexity.MEDIUM,
        ImplementationStatus.UNSUPPORTED,
        ImplementationStatus.PARTIAL,
    ),
    ApiEntry(
        "advapi32.dll",
        "RegQueryValueExW",
        "registry.read",
        ApiComplexity.MEDIUM,
        ImplementationStatus.UNSUPPORTED,
        ImplementationStatus.PARTIAL,
    ),
    ApiEntry(
        "advapi32.dll",
        "RegSetValueExW",
        "registry.write",
        ApiComplexity.MEDIUM,
        ImplementationStatus.UNSUPPORTED,
        ImplementationStatus.PARTIAL,
    ),
    # ole32
    ApiEntry(
        "ole32.dll",
        "CoInitializeEx",
        "com.initialization",
        ApiComplexity.HIGH,
        ImplementationStatus.UNSUPPORTED,
        ImplementationStatus.PARTIAL,
    ),
    ApiEntry(
        "ole32.dll",
        "CoCreateInstance",
        "com.initialization",
        ApiComplexity.HIGH,
        ImplementationStatus.UNSUPPORTED,
        ImplementationStatus.PARTIAL,
    ),
    ApiEntry(
        "ole32.dll",
        "CoUninitialize",
        "com.initialization",
        ApiComplexity.LOW,
        ImplementationStatus.UNSUPPORTED,
        ImplementationStatus.PARTIAL,
    ),
)


def _registry_key(dll: str, function: str) -> str:
    return f"{dll.lower()}::{function}"


API_REGISTRY: Dict[str, ApiEntry] = {
    _registry_key(e.dll, e.function): e for e in _CURATED
}


def lookup_api(dll: str, function: str) -> Optional[ApiEntry]:
    if function.startswith("ordinal_"):
        return None
    return API_REGISTRY.get(_registry_key(dll, function))


def classify_import(
    dll: str,
    function: str,
    *,
    provenance: Optional[ProvenanceEvidence] = None,
) -> ApiClassificationResult:
    """Classify a single imported API. Unknown APIs are marked unknown — never guessed."""
    prov = provenance or ProvenanceEvidence(
        source=REGISTRY_SOURCE,
        artifact_id=REGISTRY_VERSION,
    )
    entry = lookup_api(dll, function)
    if entry is None:
        return ApiClassificationResult(
            dll=dll.lower(),
            function=function,
            capability_id="api.unknown",
            complexity=ApiComplexity.MEDIUM,
            native_status=ImplementationStatus.UNKNOWN,
            wine_status=ImplementationStatus.UNKNOWN,
            is_known=False,
            provenance=prov,
        )
    return ApiClassificationResult(
        dll=entry.dll,
        function=entry.function,
        capability_id=entry.capability_id,
        complexity=entry.complexity,
        native_status=entry.native_status,
        wine_status=entry.wine_status,
        documentation_ref=entry.documentation_ref,
        is_known=True,
        provenance=prov,
    )


def registry_stats() -> Dict[str, object]:
    by_dll: Dict[str, Dict[str, int]] = {}
    for entry in API_REGISTRY.values():
        bucket = by_dll.setdefault(entry.dll, {"total": 0, "native_supported": 0})
        bucket["total"] += 1
        if entry.native_status == ImplementationStatus.SUPPORTED:
            bucket["native_supported"] += 1
    return {
        "total_registry_apis": len(API_REGISTRY),
        "classified_apis": len(API_REGISTRY),
        "by_dll": by_dll,
    }


def list_registry_entries() -> List[ApiEntry]:
    return sorted(API_REGISTRY.values(), key=lambda e: (e.dll, e.function))
