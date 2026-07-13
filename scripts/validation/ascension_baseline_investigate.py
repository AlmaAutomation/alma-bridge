"""Ascension baseline investigation notes for pilot-002."""

from __future__ import annotations

import hashlib
from pathlib import Path


def launcher_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def investigate() -> dict:
    nested = Path(
        "/home/joshua/.local/share/alma-bridge/prefixes/803984cf-660"
        "/drive_c/Program Files/Ascension Launcher/Ascension Launcher/Ascension Launcher.exe"
    )
    flat = Path(
        "/home/joshua/.local/share/alma-bridge/prefixes/0aaabfa5-6c9"
        "/drive_c/Program Files/Ascension Launcher/Ascension Launcher.exe"
    )
    findings = {
        "campaign_canonical_path": str(nested),
        "historical_flat_path": str(flat),
        "nested_exists": nested.exists(),
        "flat_exists": flat.exists(),
    }
    if nested.exists():
        findings["nested_sha256"] = launcher_sha256(nested)
        findings["nested_size"] = nested.stat().st_size
    if flat.exists():
        findings["flat_sha256"] = launcher_sha256(flat)
        findings["flat_size"] = flat.stat().st_size
    findings["bytes_match"] = findings.get("nested_sha256") == findings.get("flat_sha256")
    return findings


if __name__ == "__main__":
    import json

    print(json.dumps(investigate(), indent=2))
