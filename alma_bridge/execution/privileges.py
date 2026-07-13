from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import List, Optional, Tuple

_STORED_PASSWORD: Optional[str] = None
_STORED_PASSWORD_AT: Optional[float] = None
_STORED_PASSWORD_TTL_SEC = 14 * 60


def is_root() -> bool:
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def sudo_available() -> bool:
    return shutil.which("sudo") is not None


def store_sudo_password(password: Optional[str]) -> None:
    """Remember a sudo password for later API calls (e.g. the autonomous loop)."""
    global _STORED_PASSWORD, _STORED_PASSWORD_AT
    if password:
        _STORED_PASSWORD = password
        _STORED_PASSWORD_AT = time.monotonic()


def get_stored_sudo_password() -> Optional[str]:
    global _STORED_PASSWORD, _STORED_PASSWORD_AT
    if _STORED_PASSWORD_AT is None:
        return None
    if time.monotonic() - _STORED_PASSWORD_AT > _STORED_PASSWORD_TTL_SEC:
        _STORED_PASSWORD = None
        _STORED_PASSWORD_AT = None
        return None
    return _STORED_PASSWORD


def clear_stored_sudo_password() -> None:
    global _STORED_PASSWORD, _STORED_PASSWORD_AT
    _STORED_PASSWORD = None
    _STORED_PASSWORD_AT = None


def sudo_ticket_valid() -> bool:
    """True when sudo -n works (passwordless config or a recently warmed ticket)."""
    if is_root() or not sudo_available():
        return is_root()
    if passwordless_sudo_works():
        return True
    try:
        proc = subprocess.run(
            ["sudo", "-n", "true"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def sudo_is_ready(*, password: Optional[str] = None) -> bool:
    ok, _ = prepare_sudo(requested=True, password=password)
    return ok


def remember_sudo_password(password: Optional[str]) -> Tuple[bool, str]:
    """Store a UI password and warm the sudo ticket cache when possible."""
    if password:
        store_sudo_password(password)
    return prepare_sudo(requested=True, password=password)


def passwordless_sudo_works() -> bool:
    if is_root() or not sudo_available():
        return False
    try:
        proc = subprocess.run(
            ["sudo", "-n", "true"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def warm_sudo_cache(password: str) -> Tuple[bool, str]:
    """Authenticate sudo non-interactively; caches credentials for ~15 minutes."""
    if is_root() or not sudo_available() or not password:
        return False, "sudo not available"
    try:
        proc = subprocess.run(
            ["sudo", "-S", "-v"],
            input=f"{password}\n",
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode == 0:
            return True, ""
        detail = (proc.stderr or proc.stdout or "sudo authentication failed").strip()
        return False, detail
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)


def prepare_sudo(
    *,
    requested: bool,
    password: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Return (sudo_ready, error_message).
    When requested, ensure sudo works via passwordless config, a warmed ticket,
    a supplied password, or a password stored from a recent UI request.
    """
    if not requested or is_root():
        return True, ""

    if passwordless_sudo_works() or sudo_ticket_valid():
        return True, ""

    effective = password or get_stored_sudo_password()
    if effective:
        ok, detail = warm_sudo_cache(effective)
        if ok:
            store_sudo_password(effective)
            return True, ""
        if password:
            clear_stored_sudo_password()
        return False, detail or "sudo password rejected"

    return False, (
        "Sudo is enabled but no cached credentials exist. "
        "Enter your sudo password in the Bridge UI, run `sudo -v` in a terminal first, "
        "or configure passwordless sudo for Docker."
    )


def resolve_use_sudo(requested: bool | None = None) -> bool:
    """Sudo is used only for Docker sandbox — never for Wine/Proton on the host."""
    if is_root() or not requested:
        return False
    return passwordless_sudo_works()


def wrap_with_sudo(command: List[str], *, use_sudo: bool) -> List[str]:
    if not use_sudo or is_root() or not command:
        return command
    if command[0] == "sudo":
        return command
    return ["sudo", "-n", "-E", *command]
