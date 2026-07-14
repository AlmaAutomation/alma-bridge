#!/usr/bin/env python3
"""Pilot-002 setup/preflight runner — diagnostic only, not scenario execution."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from alma_bridge.validation.setup_preflight import run_setup_target

REPO_ROOT = Path(__file__).resolve().parents[2]


def _configure_profile_flags() -> None:
    os.environ.setdefault("ALMA_BRIDGE_COMPATIBILITY_PROFILES_ENABLED", "true")
    os.environ.setdefault("ALMA_BRIDGE_COMPATIBILITY_PROFILE_CREATION_ENABLED", "true")
    os.environ.setdefault("ALMA_BRIDGE_COMPATIBILITY_PROFILE_SHADOW_MODE", "true")
    os.environ.setdefault("ALMA_BRIDGE_COMPATIBILITY_PROFILE_REUSE_ENABLED", "false")


def _wineboot_prefix(prefix: Path) -> None:
    prefix.mkdir(parents=True, exist_ok=True)
    os.system(f'WINEPREFIX="{prefix}" WINEDEBUG=-all wineboot -i >/dev/null 2>&1')


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Pilot-002 setup preflight runner")
    parser.add_argument(
        "setup_id",
        choices=[
            "SETUP-T1-A",
            "SETUP-T1-B",
            "SETUP-T2-A",
            "SETUP-T2-B",
            "SETUP-T3-A",
            "SETUP-T3-B",
            "write-fallback",
        ],
    )
    parser.add_argument("--prefix-root", default=None)
    args = parser.parse_args(argv)

    _configure_profile_flags()

    prefix_root = Path(
        args.prefix_root
        or os.environ.get(
            "ALMA_BRIDGE_VALIDATION_CAMPAIGN_DISPOSABLE_ROOT",
            str(Path.home() / ".local/share/alma-bridge/prefixes/validation/pilot-002"),
        )
    ).expanduser()

    if args.setup_id.startswith("SETUP-T1"):
        script = REPO_ROOT / "scripts/validation/native_success_probe.sh"
        payload = run_setup_target(setup_id=args.setup_id, exe_path=script)
    else:
        if args.setup_id == "SETUP-T2-A":
            rel = "drive_c/windows/system32/notepad.exe"
            prefix = prefix_root / "setup/t2-notepad64-a"
        elif args.setup_id == "SETUP-T2-B":
            rel = "drive_c/windows/system32/notepad.exe"
            prefix = prefix_root / "setup/t2-notepad64-b"
        elif args.setup_id == "SETUP-T3-A":
            rel = "drive_c/Program Files/Windows NT/Accessories/wordpad.exe"
            prefix = prefix_root / "setup/t3-wordpad64-a"
        elif args.setup_id == "SETUP-T3-B":
            rel = "drive_c/Program Files/Windows NT/Accessories/wordpad.exe"
            prefix = prefix_root / "setup/t3-wordpad64-b"
        else:
            rel = "drive_c/windows/system32/write.exe"
            prefix = prefix_root / "setup/write-fallback"
        _wineboot_prefix(prefix)
        exe = prefix / rel
        if not exe.exists():
            print(json.dumps({"error": f"missing executable: {exe}"}))
            return 2
        payload = run_setup_target(
            setup_id=args.setup_id,
            exe_path=exe,
            wine_prefix=prefix,
        )

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
