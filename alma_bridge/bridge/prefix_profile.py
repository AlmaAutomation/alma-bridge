from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_PROFILE_TTL_HOURS = 24


@dataclass
class PrefixReadinessProfile:
    wine_prefix: str
    launcher_path: Optional[str] = None
    windows_version: Optional[str] = None
    dotnet_functional: bool = False
    vcrun_ready: bool = False
    wrappers_applied: bool = False
    updater_disabled: bool = False
    verified_at: str = ""
    ttl_hours: int = DEFAULT_PROFILE_TTL_HOURS

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PrefixReadinessProfile:
        return cls(
            wine_prefix=str(data.get("wine_prefix", "")),
            launcher_path=data.get("launcher_path"),
            windows_version=data.get("windows_version"),
            dotnet_functional=bool(data.get("dotnet_functional")),
            vcrun_ready=bool(data.get("vcrun_ready")),
            wrappers_applied=bool(data.get("wrappers_applied")),
            updater_disabled=bool(data.get("updater_disabled")),
            verified_at=str(data.get("verified_at", "")),
            ttl_hours=int(data.get("ttl_hours", DEFAULT_PROFILE_TTL_HOURS)),
        )


def _profile_store_dir() -> Path:
    path = Path.home() / ".local/share/alma-bridge/prefix-profiles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def profile_store_path(wine_prefix: str) -> Path:
    resolved = str(Path(wine_prefix).expanduser().resolve())
    key = hashlib.sha256(resolved.encode()).hexdigest()[:16]
    return _profile_store_dir() / f"{key}.json"


def load_prefix_profile(wine_prefix: str) -> Optional[PrefixReadinessProfile]:
    path = profile_store_path(wine_prefix)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    profile = PrefixReadinessProfile.from_dict(data)
    if not profile.wine_prefix:
        profile.wine_prefix = str(Path(wine_prefix).expanduser().resolve())
    return profile


def save_prefix_profile(profile: PrefixReadinessProfile) -> None:
    profile.verified_at = datetime.now(timezone.utc).isoformat()
    path = profile_store_path(profile.wine_prefix)
    path.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")


def profile_is_fresh(profile: PrefixReadinessProfile) -> bool:
    if not profile.verified_at:
        return False
    try:
        verified = datetime.fromisoformat(profile.verified_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if verified.tzinfo is None:
        verified = verified.replace(tzinfo=timezone.utc)
    expiry = verified + timedelta(hours=max(1, profile.ttl_hours))
    return datetime.now(timezone.utc) < expiry


def profile_allows_fast_launch(
    profile: Optional[PrefixReadinessProfile],
    wine_prefix: str,
    *,
    launcher_path: Optional[str] = None,
) -> bool:
    if profile is None or not profile_is_fresh(profile):
        return False
    if not profile.launcher_path or not profile.dotnet_functional or not profile.vcrun_ready:
        return False
    if profile.windows_version not in {None, "win10", "win11", "win2016", "win2019"}:
        return False
    if not profile.wrappers_applied or not profile.updater_disabled:
        return False
    launcher = launcher_path or profile.launcher_path
    if not Path(launcher).is_file():
        return False
    return str(Path(wine_prefix).expanduser().resolve()) == str(
        Path(profile.wine_prefix).expanduser().resolve()
    )


def invalidate_prefix_profile(wine_prefix: str) -> None:
    path = profile_store_path(wine_prefix)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
