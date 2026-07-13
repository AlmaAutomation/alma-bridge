from __future__ import annotations

import fcntl
import hashlib
import json
import os
import socket
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional

from alma_bridge.config import settings


class PrefixLockTimeout(Exception):
    """Raised when a prefix lock cannot be acquired within the timeout."""


def normalize_prefix_key(wine_prefix: str) -> str:
    return str(Path(wine_prefix).expanduser().resolve())


def prefix_lock_path(prefix_key: str) -> Path:
    digest = hashlib.sha256(prefix_key.encode("utf-8")).hexdigest()[:32]
    lock_dir = settings.data_dir / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir / f"prefix-{digest}.lock"


def _write_lock_metadata(
    handle: int,
    *,
    session_id: str,
    prefix_key: str,
    owner: str,
) -> None:
    payload = {
        "session_id": session_id,
        "prefix_key": prefix_key,
        "owner": owner,
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "acquired_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        os.lseek(handle, 0, os.SEEK_SET)
        os.ftruncate(handle, 0)
        os.write(handle, json.dumps(payload).encode("utf-8"))
    except OSError:
        pass


@contextmanager
def prefix_lock(
    wine_prefix: str,
    *,
    session_id: str,
    timeout_sec: Optional[float] = None,
    owner: Optional[str] = None,
) -> Generator[str, None, None]:
    """Acquire an exclusive flock on a stable per-prefix lock file.

    The lock file is never deleted; kernel flock ownership is authoritative.
    Metadata written to the file is diagnostic only.
    """
    prefix_key = normalize_prefix_key(wine_prefix)
    path = prefix_lock_path(prefix_key)
    timeout = timeout_sec if timeout_sec is not None else float(
        getattr(settings, "prefix_lock_timeout_sec", 120)
    )
    owner_id = owner or f"{socket.gethostname()}:{os.getpid()}"

    path.touch(exist_ok=True)
    handle = os.open(str(path), os.O_RDWR | os.O_CREAT)
    acquired = False
    deadline = time.monotonic() + max(0.1, timeout)
    try:
        while time.monotonic() < deadline:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                _write_lock_metadata(
                    handle,
                    session_id=session_id,
                    prefix_key=prefix_key,
                    owner=owner_id,
                )
                break
            except BlockingIOError:
                time.sleep(0.05)
        if not acquired:
            raise PrefixLockTimeout(
                f"Could not acquire prefix lock for {prefix_key} within {timeout}s"
            )
        yield prefix_key
    finally:
        if acquired:
            try:
                fcntl.flock(handle, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(handle)
