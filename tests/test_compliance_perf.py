from __future__ import annotations

import time

from alma_bridge.compliance._perf import (
    MAX_WORKER_CAP,
    TTLCache,
    map_concurrent,
    resolve_workers,
)


def test_ttl_cache_hit_and_miss():
    cache = TTLCache()
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return "value"

    # ttl=0 disables caching -> always recompute.
    assert cache.get_or_compute("k", 0, compute) == "value"
    assert cache.get_or_compute("k", 0, compute) == "value"
    assert calls["n"] == 2

    # ttl>0 -> second call is a hit.
    assert cache.get_or_compute("k2", 60, compute) == "value"
    assert cache.get_or_compute("k2", 60, compute) == "value"
    assert calls["n"] == 3  # only one new compute


def test_ttl_cache_expiry():
    cache = TTLCache()
    cache.set("k", "old")
    hit, value = cache.get("k", ttl=0.05)
    assert hit is True and value == "old"
    time.sleep(0.08)
    hit, _ = cache.get("k", ttl=0.05)
    assert hit is False


def test_resolve_workers_caps_and_floors():
    assert resolve_workers(1) == 1
    assert resolve_workers(0) == 1
    assert resolve_workers(1000) <= MAX_WORKER_CAP
    # Never more workers than tasks.
    assert resolve_workers(3) <= 3
    # Honor an explicit configured value (still capped).
    assert resolve_workers(100, configured=2) == 2
    assert resolve_workers(100, configured=10_000) == MAX_WORKER_CAP


def test_map_concurrent_preserves_order():
    items = list(range(20))
    out = map_concurrent(lambda x: x * x, items)
    assert out == [x * x for x in items]


def test_map_concurrent_runs_in_parallel():
    # 8 jobs that each sleep 0.1s should finish in well under the 0.8s serial time.
    started = time.perf_counter()
    out = map_concurrent(lambda x: (time.sleep(0.1) or x), list(range(8)))
    elapsed = time.perf_counter() - started
    assert out == list(range(8))
    assert elapsed < 0.5  # parallelized, not 0.8s serial


def test_map_concurrent_empty_and_single():
    assert map_concurrent(lambda x: x, []) == []
    assert map_concurrent(lambda x: x + 1, [41]) == [42]


def test_service_scan_parallel_is_fast_for_down_host():
    # Many closed ports on a black-hole address should complete quickly because
    # probes run concurrently (each connect fails fast on refusal/timeout).
    from alma_bridge.compliance.services import scan_insecure_services

    started = time.perf_counter()
    result = scan_insecure_services("127.0.0.1", ports=[21, 23, 25, 110, 143, 512, 513, 514], timeout=0.5)
    elapsed = time.perf_counter() - started
    assert result["scanned_ports"] == 8
    # 8 sequential 0.5s timeouts would be 4s; parallel should be far less.
    assert elapsed < 2.0
