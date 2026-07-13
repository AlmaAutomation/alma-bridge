"""Heavy / recursive stress tests for the compliance suite.

These run entirely against loopback (no external network) but exercise the real
concurrency, caching, and bridge machinery under load to surface thread/FD
leaks and races.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import ssl
import subprocess
import threading
import time

import pytest

from alma_bridge.compliance._perf import TTLCache, map_concurrent
from alma_bridge.compliance.bridge import TlsModernizer


def _fd_count() -> int:
    try:
        return len(os.listdir("/proc/self/fd"))
    except OSError:
        return -1


# --------------------------------------------------------------------------- #
# TTL cache under concurrency
# --------------------------------------------------------------------------- #


def test_ttl_cache_concurrent_single_compute():
    cache = TTLCache()
    compute_count = {"n": 0}
    lock = threading.Lock()

    def compute():
        with lock:
            compute_count["n"] += 1
        time.sleep(0.01)
        return "v"

    def worker():
        for _ in range(200):
            assert cache.get_or_compute("hot-key", ttl=30, compute=compute) == "v"

    threads = [threading.Thread(target=worker) for _ in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 40 threads x 200 reads of one hot key; compute may race a few times at the
    # very start but must not run for every call.
    assert compute_count["n"] < 50


def test_ttl_cache_many_keys_no_corruption():
    cache = TTLCache()

    def worker(base):
        for i in range(500):
            key = (base, i % 50)
            cache.set(key, base * 1000 + (i % 50))
            hit, val = cache.get(key, ttl=30)
            if hit:
                assert val == base * 1000 + (i % 50)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


# --------------------------------------------------------------------------- #
# Concurrency primitives: bounded threads, no leak across many calls
# --------------------------------------------------------------------------- #


def test_map_concurrent_recursive_no_thread_explosion():
    baseline = threading.active_count()
    peak = {"n": baseline}
    plock = threading.Lock()

    def leaf(x):
        with plock:
            peak["n"] = max(peak["n"], threading.active_count())
        time.sleep(0.005)
        return x

    def mid(group):
        # Nested concurrency: each parallel task itself fans out.
        return map_concurrent(leaf, list(range(10)))

    # 30 outer tasks each spawning an inner fan-out of 10 => naive nesting could
    # explode into hundreds of live threads.
    out = map_concurrent(mid, list(range(30)))
    assert len(out) == 30
    assert all(r == list(range(10)) for r in out)
    # With the nesting guard, threads stay bounded to one full fan-out level
    # (outer cap) plus a small nested budget per worker, not items x items.
    assert peak["n"] < baseline + 96, f"thread peak too high: {peak['n']} (base {baseline})"


def test_repeated_map_concurrent_no_leak():
    baseline = threading.active_count()
    for _ in range(100):
        out = map_concurrent(lambda x: x + 1, list(range(16)))
        assert out == list(range(1, 17))
    time.sleep(0.2)
    assert threading.active_count() <= baseline + 2


# --------------------------------------------------------------------------- #
# TLS bridge under heavy concurrent load
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl not available")
def test_bridge_many_concurrent_connections(tmp_path):
    cert = tmp_path / "c.pem"
    key = tmp_path / "k.pem"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", str(key),
         "-out", str(cert), "-days", "1", "-nodes", "-subj", "/CN=localhost"],
        check=True, capture_output=True,
    )

    async def run():
        server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ctx.load_cert_chain(certfile=str(cert), keyfile=str(key))

        async def echo(reader, writer):
            data = await reader.read(256)
            writer.write(b"R:" + data)
            await writer.drain()
            writer.close()

        upstream = await asyncio.start_server(echo, "127.0.0.1", 0, ssl=server_ctx)
        uport = upstream.sockets[0].getsockname()[1]

        fd_before = _fd_count()
        mod = TlsModernizer()
        spec = await mod.start("127.0.0.1", uport, listen_port=0, verify=False,
                               upstream_sni="localhost")

        async def one(i):
            r, w = await asyncio.open_connection("127.0.0.1", spec.listen_port)
            payload = f"msg{i}".encode()
            w.write(payload)
            await w.drain()
            if w.can_write_eof():
                w.write_eof()
            resp = await asyncio.wait_for(r.read(256), timeout=10)
            w.close()
            return resp

        results = await asyncio.gather(*[one(i) for i in range(100)])
        assert all(res == b"R:" + f"msg{i}".encode() for i, res in enumerate(results))
        assert spec.total_connections == 100

        await mod.stop(spec.id)
        upstream.close()
        await upstream.wait_closed()
        await asyncio.sleep(0.2)

        fd_after = _fd_count()
        # Allow a little slack but ensure we did not leak ~100 sockets.
        if fd_before != -1:
            assert fd_after <= fd_before + 10, f"fd leak: {fd_before} -> {fd_after}"

    asyncio.run(run())


# --------------------------------------------------------------------------- #
# Recursive heavy report runs: no thread/FD leak
# --------------------------------------------------------------------------- #


def test_repeated_reports_no_resource_leak():
    from alma_bridge.compliance.report import build_compliance_report

    baseline_threads = threading.active_count()
    fd_before = _fd_count()
    for _ in range(40):
        report = build_compliance_report(
            targets=[],
            include_drivers=True,
            include_shims=True,
            check_time=False,  # no network
            sys_root="/sys",
        )
        assert "overall_compliant" in report
    time.sleep(0.3)
    assert threading.active_count() <= baseline_threads + 2
    if fd_before != -1:
        assert _fd_count() <= fd_before + 10


# --------------------------------------------------------------------------- #
# Autopilot under heavy / concurrent / recursive load
# --------------------------------------------------------------------------- #


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    from alma_bridge.compliance import learning

    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "outcomes.db")
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    learning.init_healing_store()
    return tmp_path


_ERROR_CORPUS = [
    "error while loading shared libraries: libssl.so.1.0.0: cannot open shared object file",
    "version `GLIBC_2.34' not found",
    "cannot execute binary file: Exec format error (ELFCLASS32)",
    "sslv3 alert handshake failure unsupported protocol",
    "SSL: CERTIFICATE_VERIFY_FAILED unable to get local issuer certificate",
    "curl: (6) Could not resolve host: example.com",
    "modprobe: FATAL: no driver found for device",
    "json-rpc eth_chainId endpoint unreachable",
    "permission denied",
    "the flux capacitor overheated",  # unknown
]


def test_autopilot_diagnose_plan_fuzz_recursive(isolated_db):
    """Many recursive diagnose+plan passes never crash and stay well-formed."""
    from alma_bridge.compliance import autopilot

    for i in range(2000):
        text = _ERROR_CORPUS[i % len(_ERROR_CORPUS)]
        # Mutate the input to exercise the regexes with noise.
        noisy = f"[{i}] {text.upper() if i % 3 else text} \x00\t{i}"
        plan = autopilot.plan_pathways(noisy, os_release="ID=ubuntu\nID_LIKE=debian")
        assert plan["pathways"], "every diagnosis must yield at least one pathway"
        assert plan["primary_signature"]
        for path in plan["pathways"]:
            for step in path["steps"]:
                cmd = step.get("command") or ""
                assert "{pm-" not in cmd  # no unresolved placeholders


def test_autopilot_learning_store_concurrent_writes(isolated_db):
    """Hammer the SQLite learning store from many threads — no lock errors,
    and the recorded counts are exactly correct (no lost updates)."""
    from alma_bridge.compliance import autopilot, learning

    signatures = ["tls_obsolete_protocol", "dns_failure", "missing_shared_library"]
    pathways = ["pw_a", "pw_b", "pw_c"]
    writers = 24
    per_writer = 50
    errors: list = []

    def worker(wid):
        try:
            for n in range(per_writer):
                sig = signatures[(wid + n) % len(signatures)]
                pw = pathways[n % len(pathways)]
                autopilot.record_outcome(sig, pw, success=(n % 2 == 0))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(w,)) for w in range(writers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"concurrent writes raised: {errors[:3]}"

    # Total attempts recorded must equal exactly writers * per_writer.
    total_attempts = sum(
        row["attempts"] for row in learning.feedback_summary(limit=500)
    )
    assert total_attempts == writers * per_writer, (
        f"lost updates under contention: {total_attempts} != {writers * per_writer}"
    )


def test_autopilot_concurrent_read_write_mix(isolated_db):
    """Readers (plan/diagnose) and writers (feedback) racing must not crash or
    corrupt ranking; the learned leader must win deterministically afterwards."""
    from alma_bridge.compliance import autopilot

    stop = threading.Event()
    errors: list = []

    def reader():
        try:
            while not stop.is_set():
                autopilot.plan_pathways("unsupported protocol handshake failure")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    def writer():
        try:
            for _ in range(150):
                autopilot.record_outcome("tls_obsolete_protocol", "tls_enable_modern_openssl", True)
                autopilot.record_outcome("tls_obsolete_protocol", "tls_modernizer_bridge", False)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    readers = [threading.Thread(target=reader) for _ in range(6)]
    writers = [threading.Thread(target=writer) for _ in range(3)]
    for t in readers + writers:
        t.start()
    for t in writers:
        t.join()
    stop.set()
    for t in readers:
        t.join()

    assert not errors, f"read/write race raised: {errors[:3]}"
    final = autopilot.plan_pathways("unsupported protocol handshake failure")
    assert final["pathways"][0]["id"] == "tls_enable_modern_openssl"


def test_legacy32_concurrent_assess_and_plan(isolated_db):
    """Concurrent assess/plan calls (subprocess + fs probes) never crash."""
    from alma_bridge.compliance import legacy32

    errors: list = []

    def worker():
        try:
            for _ in range(40):
                a = legacy32.assess_32bit_support()
                legacy32.plan_32bit_enablement(a, os_release="ID=fedora")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, f"legacy32 concurrency raised: {errors[:3]}"
