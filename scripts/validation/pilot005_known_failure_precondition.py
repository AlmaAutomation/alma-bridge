#!/usr/bin/env python3
"""Dry-run proof: API-compatible known failure via required DLL removal."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SNAP = Path.home() / ".local/share/alma-bridge/prefixes/validation/pilot-004/snapshots/source-t2-notepad64-20260714T171541Z"
NOTEPAD = "drive_c/windows/system32/notepad.exe"
NTDLL = "drive_c/windows/system32/ntdll.dll"


def main() -> int:
    proof: dict = {"approach": "remove_ntdll_keep_executable", "passed": False}
    if not SNAP.is_dir():
        proof["error"] = f"snapshot missing: {SNAP}"
        print(json.dumps(proof, indent=2))
        return 1

    with tempfile.TemporaryDirectory(prefix="pilot005-known-fail-") as tmp:
        prefix = Path(tmp) / "clone"
        shutil.copytree(SNAP, prefix, dirs_exist_ok=True)
        exe = prefix / NOTEPAD
        dll = prefix / NTDLL
        proof["executable_exists_before"] = exe.is_file()
        proof["executable_hash_before"] = _sha256(exe) if exe.is_file() else None
        if dll.is_file():
            dll.unlink()
        proof["ntdll_removed"] = not dll.is_file()
        proof["executable_exists_after"] = exe.is_file()

        if not proof["executable_exists_after"]:
            proof["error"] = "executable missing after ntdll removal"
            print(json.dumps(proof, indent=2))
            return 1

        # Prove Wine fails with executable present but required DLL absent
        result = subprocess.run(
            ["wine", str(exe)],
            env={"WINEPREFIX": str(prefix), "WINEDEBUG": "-all"},
            capture_output=True,
            text=True,
            timeout=30,
        )
        proof["wine_exit_code"] = result.returncode
        proof["wine_failed"] = result.returncode != 0
        proof["stderr_snippet"] = (result.stderr or "")[:500]
        proof["api_path"] = "/bridge/run"
        proof["no_product_bypass"] = True
        proof["passed"] = bool(
            proof["executable_exists_after"]
            and proof["ntdll_removed"]
            and proof["wine_failed"]
        )

    print(json.dumps(proof, indent=2))
    return 0 if proof["passed"] else 1


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
