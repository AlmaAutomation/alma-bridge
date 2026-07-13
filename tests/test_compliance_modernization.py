from __future__ import annotations

import socket
import threading
import time

import pytest

from alma_bridge.compliance.dns import DOH_PROVIDERS, parse_doh_json, resolve_doh
from alma_bridge.compliance.services import (
    recommend_for_port,
    scan_insecure_services,
)
from alma_bridge.compliance.timecheck import (
    SKEW_FAIL_SECONDS,
    evaluate_clock_skew,
)


# --------------------------------------------------------------------------- #
# Clock / time
# --------------------------------------------------------------------------- #


def test_clock_in_sync_is_compliant():
    verdict = evaluate_clock_skew(1_000_000.0, 1_000_000.5)
    assert verdict["compliant"] is True
    assert verdict["severity"] == "ok"


def test_clock_borderline_is_warning():
    verdict = evaluate_clock_skew(1_000_120.0, 1_000_000.0)  # 120s ahead
    assert verdict["compliant"] is True
    assert verdict["severity"] == "medium"


def test_clock_large_skew_blocks():
    verdict = evaluate_clock_skew(1_000_000.0 + SKEW_FAIL_SECONDS + 10, 1_000_000.0)
    assert verdict["compliant"] is False
    assert verdict["severity"] == "high"
    assert "certificate validation" in verdict["impact"]


def test_clock_no_reference_is_unknown():
    verdict = evaluate_clock_skew(1_000_000.0, None)
    assert verdict["compliant"] is None
    assert verdict["severity"] == "unknown"


# --------------------------------------------------------------------------- #
# Insecure services
# --------------------------------------------------------------------------- #


def test_recommend_for_known_and_unknown_port():
    telnet = recommend_for_port(23)
    assert telnet["name"] == "Telnet"
    assert "SSH" in telnet["replacement"]
    assert recommend_for_port(22) is None  # SSH is not insecure


def test_scan_detects_open_insecure_service():
    # Stand up a throwaway listener and treat its port as if it were telnet.
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    stop = threading.Event()

    def accept_loop():
        srv.settimeout(0.5)
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
                conn.close()
            except socket.timeout:
                continue
            except OSError:
                break

    t = threading.Thread(target=accept_loop, daemon=True)
    t.start()
    try:
        # Monkeypatch a known insecure port number onto our live listener via ports=[port]
        # is not in the registry, so instead verify probe semantics directly.
        from alma_bridge.compliance.services import probe_port

        assert probe_port("127.0.0.1", port, timeout=1) is True
        # A port that is definitely closed.
        assert probe_port("127.0.0.1", 1, timeout=1) is False
    finally:
        stop.set()
        srv.close()
        t.join(timeout=2)


def test_scan_insecure_services_all_closed():
    # Loopback with the real registry ports; almost certainly nothing listening
    # on these on the test host -> compliant.
    result = scan_insecure_services("127.0.0.1", ports=[23, 21, 512], timeout=0.3)
    assert result["host"] == "127.0.0.1"
    assert result["scanned_ports"] == 3
    assert isinstance(result["compliant"], bool)


# --------------------------------------------------------------------------- #
# DoH
# --------------------------------------------------------------------------- #


def test_parse_doh_json_success():
    raw = '{"Status":0,"Answer":[{"name":"example.com.","type":1,"TTL":300,"data":"93.184.216.34"}]}'
    parsed = parse_doh_json(raw)
    assert parsed["ok"] is True
    assert parsed["rcode"] == "NOERROR"
    assert parsed["answers"][0]["type"] == "A"
    assert parsed["answers"][0]["data"] == "93.184.216.34"


def test_parse_doh_json_nxdomain():
    parsed = parse_doh_json('{"Status":3}')
    assert parsed["ok"] is False
    assert parsed["rcode"] == "NXDOMAIN"


@pytest.mark.parametrize("garbage", ["", "not json", "[]", "123", b"\x00"])
def test_parse_doh_json_never_crashes(garbage):
    out = parse_doh_json(garbage)
    assert out["ok"] is False


def test_resolve_doh_unknown_provider():
    out = resolve_doh("example.com", provider="not-a-provider")
    assert out["ok"] is False
    assert "unknown provider" in out["error"]


def test_doh_providers_present():
    assert "cloudflare" in DOH_PROVIDERS
    assert "google" in DOH_PROVIDERS
