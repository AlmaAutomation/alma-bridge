"""Performance helpers for the compliance suite (designed to run on low-end
hardware).

Two primitives:

* :class:`TTLCache` — a tiny thread-safe time-to-live cache so repeated or
  overlapping probes (e.g. the same host appearing as a TLS target and a web3
  RPC host) are computed once.
* :func:`resolve_workers` / :func:`map_concurrent` — bounded I/O concurrency.
  All compliance work is network-bound, so a handful of threads hide latency
  even on a single core, while the cap keeps memory tiny on a "potato".
"""

from __future__ import annotations

import contextlib
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

T = TypeVar("T")
R = TypeVar("R")

# Hard ceiling so we never spawn a thread storm on a tiny box.
MAX_WORKER_CAP = 16
# When already inside a parallel worker, nested fan-outs use a much smaller
# budget so threads don't multiply (outer_cap x inner_cap stays bounded).
NESTED_WORKER_CAP = 4

# Tracks whether the current thread is already executing inside a compliance
# worker, so nested map_concurrent/run_jobs calls shrink their pools.
_depth = threading.local()

# Global hard cap on concurrent *network* operations (sockets/handshakes),
# independent of how deeply parallelism nests. Protects FD limits and CPU on
# low-end hosts. Sized lazily; reconfigurable via set_network_concurrency.
_net_lock = threading.Lock()
_net_semaphore = threading.BoundedSemaphore(MAX_WORKER_CAP)
_net_limit = MAX_WORKER_CAP


def set_network_concurrency(limit: int) -> None:
    """Resize the global cap on concurrent network operations."""
    global _net_semaphore, _net_limit
    limit = max(1, min(int(limit), 256))
    with _net_lock:
        _net_semaphore = threading.BoundedSemaphore(limit)
        _net_limit = limit


@contextlib.contextmanager
def network_slot():
    """Acquire a global network slot for the duration of one socket operation.

    Only leaf I/O should hold a slot (never orchestration), so nesting cannot
    deadlock — it simply throttles total concurrent connections.
    """
    with _net_lock:
        sem = _net_semaphore
    sem.acquire()
    try:
        yield
    finally:
        sem.release()


def _in_worker() -> bool:
    return getattr(_depth, "active", False)


def _wrap(func: Callable[..., R]) -> Callable[..., R]:
    """Mark the calling thread as inside a worker while ``func`` runs."""

    def inner(*args: Any, **kwargs: Any) -> R:
        prev = getattr(_depth, "active", False)
        _depth.active = True
        try:
            return func(*args, **kwargs)
        finally:
            _depth.active = prev

    return inner


class TTLCache:
    """Minimal thread-safe TTL cache."""

    def __init__(self) -> None:
        self._store: Dict[Any, Tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: Any, ttl: float) -> Tuple[bool, Any]:
        """Return ``(hit, value)``. Miss if absent or older than ``ttl``."""
        if ttl <= 0:
            return False, None
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return False, None
            stored_at, value = entry
            if now - stored_at > ttl:
                self._store.pop(key, None)
                return False, None
            return True, value

    def set(self, key: Any, value: Any) -> None:
        with self._lock:
            self._store[key] = (time.monotonic(), value)

    def get_or_compute(self, key: Any, ttl: float, compute: Callable[[], Any]) -> Any:
        hit, value = self.get(key, ttl)
        if hit:
            return value
        value = compute()
        if ttl > 0:
            self.set(key, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


def resolve_workers(n_tasks: int, configured: int = 0) -> int:
    """Choose a bounded worker count for ``n_tasks`` I/O-bound jobs.

    ``configured`` > 0 forces a value (still capped). Otherwise auto-tune from
    CPU count but stay small so memory stays tiny on low-end hardware. When
    called from inside another worker, the budget shrinks to avoid a thread
    storm from nested fan-outs.
    """
    if n_tasks <= 1:
        return 1
    cap = NESTED_WORKER_CAP if _in_worker() else MAX_WORKER_CAP
    if configured and configured > 0:
        return max(1, min(configured, n_tasks, cap))
    cpu = os.cpu_count() or 1
    # I/O bound: allow a few threads per core to hide network latency, capped.
    auto = max(4, cpu * 2)
    return max(1, min(auto, n_tasks, cap))


def map_concurrent(
    func: Callable[[T], R],
    items: List[T],
    *,
    configured_workers: int = 0,
) -> List[R]:
    """Run ``func`` over ``items`` concurrently, preserving input order."""
    if not items:
        return []
    if len(items) == 1:
        return [_wrap(func)(items[0])]
    workers = resolve_workers(len(items), configured_workers)
    wrapped = _wrap(func)
    results: List[Optional[R]] = [None] * len(items)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(wrapped, item): idx for idx, item in enumerate(items)}
        for future in futures:
            idx = futures[future]
            results[idx] = future.result()
    return results  # type: ignore[return-value]


def run_jobs(
    jobs: List[Tuple[Any, Callable[[], R]]],
    *,
    configured_workers: int = 0,
) -> Dict[Any, R]:
    """Run keyed zero-arg jobs concurrently; return ``{key: result}``.

    Each job runs marked as a worker, so any nested ``map_concurrent`` inside a
    job shrinks its pool (bounding total threads to one level of fan-out).
    """
    if not jobs:
        return {}
    if len(jobs) == 1:
        key, fn = jobs[0]
        return {key: _wrap(fn)()}
    workers = resolve_workers(len(jobs), configured_workers)
    results: Dict[Any, R] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_wrap(fn)): key for key, fn in jobs}
        for future in futures:
            results[futures[future]] = future.result()
    return results
