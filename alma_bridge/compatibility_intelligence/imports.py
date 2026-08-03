"""Import extraction and DLL dependency graph building."""

from __future__ import annotations

from typing import List

from alma_bridge.compatibility_intelligence.models import ImportGraphEdge, ImportedFunction
from alma_bridge.native_runtime.pe.imports import ImportDescriptor
from alma_bridge.native_runtime.pe.parser import ParsedPE


def extract_imports(parsed: ParsedPE) -> List[ImportedFunction]:
    """Flatten PE import descriptors into imported function records."""
    results: List[ImportedFunction] = []
    for desc in parsed.imports:
        dll = desc.dll_name.lower()
        for fn in desc.functions:
            is_ordinal = fn.startswith("ordinal_")
            results.append(ImportedFunction(dll=dll, name=fn, is_ordinal=is_ordinal))
    return sorted(results, key=lambda i: (i.dll, i.name))


def build_import_graph(parsed: ParsedPE) -> List[ImportGraphEdge]:
    """Build application → DLL import graph edges."""
    app_label = parsed.file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    edges: List[ImportGraphEdge] = []
    for desc in parsed.imports:
        edges.append(
            ImportGraphEdge(
                source_dll=app_label,
                target_dll=desc.dll_name.lower(),
                functions=sorted(desc.functions),
            )
        )
    for delay_dll in parsed.delay_import_dlls:
        edges.append(
            ImportGraphEdge(
                source_dll=app_label,
                target_dll=delay_dll.lower(),
                functions=["<delay-load>"],
            )
        )
    return sorted(edges, key=lambda e: (e.target_dll, e.source_dll))


def detect_forwarded_imports(descriptors: List[ImportDescriptor]) -> List[str]:
    """Detect import names that look like export forwarders (DLL.function pattern)."""
    forwarded: List[str] = []
    for desc in descriptors:
        for fn in desc.functions:
            if "." in fn and not fn.startswith("ordinal_"):
                forwarded.append(f"{desc.dll_name}!{fn}")
    return sorted(forwarded)
