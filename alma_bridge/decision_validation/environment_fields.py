"""Environment field classification for dry-run feasibility."""

from __future__ import annotations

from typing import Iterable, Tuple

# Fully recognized session environment keys — no warning emitted.
ENV_KNOWN_KEYS = frozenset(
    {
        "WINEPREFIX",
        "WINEDLLOVERRIDES",
        "WINEDEBUG",
        "DISPLAY",
    }
)

# Legacy keys that may be present but are not required to conclude feasibility.
ENV_OPTIONAL_LEGACY_KEYS = frozenset(
    {
        "LD_LIBRARY_PATH",
        "LD_PRELOAD",
        "PATH",
        "HOME",
        "USER",
        "SHELL",
        "PWD",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TMPDIR",
        "XDG_RUNTIME_DIR",
        "DBUS_SESSION_BUS_ADDRESS",
    }
)


def classify_environment_fields(env_fields: dict) -> Tuple[list[str], list[str]]:
    """Return (optional_unknown, required_unknown) field names from session env."""
    optional_unknown: list[str] = []
    required_unknown: list[str] = []
    for key in sorted(env_fields):
        if key in ENV_KNOWN_KEYS:
            continue
        if key in ENV_OPTIONAL_LEGACY_KEYS:
            optional_unknown.append(key)
        else:
            required_unknown.append(key)
    return optional_unknown, required_unknown


def format_field_list(fields: Iterable[str]) -> str:
    return ", ".join(fields)
