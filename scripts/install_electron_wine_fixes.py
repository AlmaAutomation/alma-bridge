#!/usr/bin/env python3
"""Force-install Alma's Electron-on-Wine fixes for an installed launcher.

Usage:
  python scripts/install_electron_wine_fixes.py \
    "/path/to/prefix/.../Ascension Launcher.exe"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running from repo root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alma_bridge.compatibility.electron_wine import prepare_electron_wine


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    app = sys.argv[1]
    if not Path(app).exists():
        print(f"File not found: {app}", file=sys.stderr)
        return 1
    report = prepare_electron_wine(app)
    print(json.dumps(report, indent=2))
    resources = Path(report["resources"] or "")
    guard = resources / "alma-guard"
    sidecar = resources / "AscensionClientServices.exe"
    ok = guard.exists() and any(guard.iterdir())
    wrapper = sidecar.exists() and b"alma-cs-wrapper-decoy-v1" in sidecar.read_bytes()
    print()
    print(f"alma-guard present: {ok}")
    print(f"wrapper has decoy support: {wrapper}")
    return 0 if ok and wrapper else 1


if __name__ == "__main__":
    raise SystemExit(main())
