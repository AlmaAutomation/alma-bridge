from __future__ import annotations

from pathlib import Path
from typing import List, Optional


def find_proton_installs() -> List[str]:
    """Discover Proton compatibility tool executables on the host."""
    roots = [
        Path.home() / ".steam" / "root" / "compatibilitytools.d",
        Path.home() / ".local" / "share" / "Steam" / "compatibilitytools.d",
        Path.home() / ".steam" / "debian-installation" / "compatibilitytools.d",
    ]

    steam_common = Path.home() / ".steam" / "root" / "steamapps" / "common"
    if steam_common.exists():
        roots.extend(sorted(steam_common.glob("Proton*")))

    local_common = Path.home() / ".local" / "share" / "Steam" / "steamapps" / "common"
    if local_common.exists():
        roots.extend(sorted(local_common.glob("Proton*")))

    found: List[str] = []
    seen: set[str] = set()

    for root in roots:
        if not root.exists():
            continue
        candidates = [root] if root.is_dir() and root.name.startswith("Proton") else root.iterdir()
        for entry in candidates:
            if not entry.is_dir():
                continue
            for proton_name in ("proton", "proton-run"):
                proton_bin = entry / proton_name
                if proton_bin.exists():
                    resolved = str(proton_bin.resolve())
                    if resolved not in seen:
                        seen.add(resolved)
                        found.append(resolved)

    return found


def find_best_proton() -> Optional[str]:
    installs = find_proton_installs()
    return installs[0] if installs else None
