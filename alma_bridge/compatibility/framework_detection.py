from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

WX_IMPORT_DLL_RE = re.compile(r"^wx(?:msw|base)\d+.*\.dll$", re.IGNORECASE)
WX_BINARY_DLL_RE = re.compile(r"wx(?:msw|base)\d+\w*\.dll", re.IGNORECASE)
WX_EMBEDDED_RE = re.compile(r"wxwidgets\d*|include/wx/", re.IGNORECASE)
WX_VERSION_RE = re.compile(r"wxwidgets\s+([\d.]+(?:\.[\d]+)*)", re.IGNORECASE)
WX_BUNDLED_DLL_PREFIXES = ("wxmsw", "wxbase")


@dataclass(frozen=True)
class GuiFrameworkDetection:
    framework: str
    confidence: float
    version: Optional[str] = None
    linkage: str = "unknown"
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "framework": self.framework,
            "confidence": self.confidence,
            "version": self.version,
            "linkage": self.linkage,
            "evidence": list(self.evidence),
        }


def _pe_import_dlls(path: Path) -> List[str]:
    try:
        result = subprocess.run(
            ["objdump", "-p", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return []
        return [
            line.split("DLL Name:")[-1].strip()
            for line in result.stdout.splitlines()
            if "DLL Name:" in line
        ]
    except (OSError, subprocess.TimeoutExpired):
        return []


def _scan_binary_wx_signatures(path: Path) -> List[str]:
    try:
        data = path.read_bytes()
    except OSError:
        return []
    text = data.decode("latin-1", errors="ignore")
    evidence: List[str] = []
    for match in WX_EMBEDDED_RE.finditer(text):
        snippet = match.group(0)[:120]
        entry = f"embedded_string:{snippet}"
        if entry not in evidence:
            evidence.append(entry)
    for dll in sorted(set(WX_BINARY_DLL_RE.findall(text))):
        entry = f"binary_dll_reference:{dll}"
        if entry not in evidence:
            evidence.append(entry)
    return evidence


def _bundled_wx_dlls(directory: Path) -> List[str]:
    if not directory.is_dir():
        return []
    found: List[str] = []
    for entry in directory.iterdir():
        if not entry.is_file():
            continue
        name = entry.name
        lower = name.lower()
        if lower.endswith(".dll") and lower.startswith(WX_BUNDLED_DLL_PREFIXES):
            found.append(name)
    return sorted(found)


def is_wxwidgets_dll_name(name: str) -> bool:
    return bool(WX_IMPORT_DLL_RE.match(name))


def detect_gui_framework(
    path: str | Path,
    *,
    runtime_log: str = "",
) -> GuiFrameworkDetection:
    """Detect GUI toolkit/framework evidence for a Windows PE executable."""
    target = Path(path).expanduser()
    evidence: List[str] = []
    wx_imports: List[str] = []
    version: Optional[str] = None
    linkage = "unknown"

    if target.is_file():
        for dll in _pe_import_dlls(target):
            if is_wxwidgets_dll_name(dll):
                wx_imports.append(dll)
                evidence.append(f"pe_import:{dll}")
        if wx_imports:
            linkage = "dynamic"

        for item in _scan_binary_wx_signatures(target):
            if item not in evidence:
                evidence.append(item)

        for dll_name in _bundled_wx_dlls(target.parent):
            evidence.append(f"bundled_dll:{dll_name}")
            if linkage == "unknown":
                linkage = "dynamic"

    if runtime_log:
        lower_log = runtime_log.lower()
        if "wxwidgets" in lower_log:
            evidence.append("runtime_banner:wxwidgets")
            match = WX_VERSION_RE.search(runtime_log)
            if match:
                version = match.group(1)
                evidence.append(f"runtime_version:{version}")

    if evidence and not wx_imports:
        if any(
            item.startswith(("embedded_string:", "binary_dll_reference:"))
            for item in evidence
        ):
            linkage = "static" if linkage == "unknown" else linkage

    if not evidence:
        return GuiFrameworkDetection(
            framework="unknown",
            confidence=0.0,
            version=None,
            linkage="unknown",
            evidence=[],
        )

    confidence = 0.45
    if wx_imports:
        confidence += 0.35
    if any(item.startswith("bundled_dll:") for item in evidence):
        confidence += 0.1
    if any(item.startswith("runtime_") for item in evidence):
        confidence += 0.1
    if version:
        confidence += 0.05

    return GuiFrameworkDetection(
        framework="wxwidgets",
        confidence=min(confidence, 0.99),
        version=version,
        linkage=linkage,
        evidence=evidence,
    )
