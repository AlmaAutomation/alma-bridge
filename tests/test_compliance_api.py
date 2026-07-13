from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alma_bridge.main import create_app


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def test_web3_chains(client):
    resp = client.get("/compliance/web3/chains")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 1
    assert "1" in body["chains"] or 1 in body["chains"]


def test_web3_ipfs_url(client):
    resp = client.post(
        "/compliance/web3/ipfs-url",
        json={"uri": "ipfs://QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["url"].endswith("/ipfs/QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG")
    assert body["valid_cid"] is True


def test_web3_ipfs_url_requires_uri(client):
    resp = client.post("/compliance/web3/ipfs-url", json={"uri": "   "})
    assert resp.status_code == 400


def test_drivers_inventory(client):
    resp = client.get("/compliance/drivers")
    assert resp.status_code == 200
    body = resp.json()
    assert "device_count" in body
    assert isinstance(body["devices"], list)
    assert isinstance(body["compliant"], bool)


def test_tls_assess_requires_host(client):
    resp = client.post("/compliance/tls/assess", json={"host": "", "port": 443})
    assert resp.status_code == 400


def test_tls_assess_unreachable_host(client):
    # .invalid never resolves -> exercises the unreachable path, no real network.
    resp = client.post(
        "/compliance/tls/assess",
        json={"host": "no-such-host.invalid", "port": 443, "timeout": 3, "probe_legacy": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["compliant"] is False
    assert body["reachable"] is False
    assert body["grade"] == "unreachable"


def test_tls_bridge_lifecycle(client):
    # Start a bridge (binds a real ephemeral listener); upstream need not exist yet.
    start = client.post(
        "/compliance/tls/bridge",
        json={"upstream_host": "127.0.0.1", "upstream_port": 65001, "listen_port": 0},
    )
    assert start.status_code == 200
    info = start.json()
    bridge_id = info["id"]
    assert info["listen"].startswith("127.0.0.1:")
    assert info["upstream"] == "127.0.0.1:65001"

    listing = client.get("/compliance/tls/bridges").json()
    assert any(b["id"] == bridge_id for b in listing["bridges"])

    stop = client.delete(f"/compliance/tls/bridge/{bridge_id}")
    assert stop.status_code == 200
    assert stop.json()["stopped"] is True

    # Second stop -> not found
    assert client.delete(f"/compliance/tls/bridge/{bridge_id}").status_code == 404


def test_web3_assess_unreachable(client):
    # Port 1 on loopback refuses immediately -> unreachable, no external network.
    resp = client.post(
        "/compliance/web3/assess",
        json={"rpc_url": "http://127.0.0.1:1/", "timeout": 3, "check_tls": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["web3_ready"] is False
    assert body["blockers"]


def test_web3_assess_bad_scheme(client):
    resp = client.post(
        "/compliance/web3/assess",
        json={"rpc_url": "ftp://example.com", "check_tls": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["web3_ready"] is False


def test_compliance_scan_no_targets(client):
    # check_time False to avoid a live NTP query in CI.
    resp = client.post(
        "/compliance/scan",
        json={"targets": [], "include_shims": False, "check_time": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "overall_compliant" in body
    assert body["summary"]["tls_targets"] == 0
    assert "os" in body["host"]


def test_ca_bundle_download(client):
    resp = client.get("/compliance/tls/ca-bundle")
    assert resp.status_code == 200
    assert "BEGIN CERTIFICATE" in resp.text
    assert resp.headers["content-type"].startswith("application/x-pem-file")


def test_services_scan_requires_host(client):
    resp = client.post("/compliance/services/scan", json={"host": "  "})
    assert resp.status_code == 400


def test_services_scan_loopback_closed_ports(client):
    resp = client.post(
        "/compliance/services/scan",
        json={"host": "127.0.0.1", "ports": [23, 21], "timeout": 0.3},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["scanned_ports"] == 2
    assert isinstance(body["compliant"], bool)


def test_dns_resolve_unknown_provider(client):
    resp = client.post(
        "/compliance/dns/resolve",
        json={"name": "example.com", "provider": "nope"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "unknown provider" in body["error"]


def test_dns_resolve_requires_name(client):
    resp = client.post("/compliance/dns/resolve", json={"name": ""})
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# Autopilot
# --------------------------------------------------------------------------- #


def test_autopilot_diagnose(client):
    resp = client.post(
        "/compliance/autopilot/diagnose",
        json={"error_text": "error while loading shared libraries: libfoo.so.2: cannot open shared object file"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["diagnoses"][0]["signature"] == "missing_shared_library"


def test_autopilot_diagnose_requires_text(client):
    resp = client.post("/compliance/autopilot/diagnose", json={"error_text": "  "})
    assert resp.status_code == 400


def test_autopilot_run_dry(client):
    resp = client.post(
        "/compliance/autopilot/run",
        json={"error_text": "sslv3 alert handshake failure unsupported protocol", "execute": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["primary_signature"] == "tls_obsolete_protocol"
    assert body["mutations_applied"] is False
    assert len(body["pathways"]) >= 1


def test_autopilot_feedback(client):
    resp = client.post(
        "/compliance/autopilot/feedback",
        json={"signature": "dns_failure", "pathway_id": "dns_over_https", "success": True},
    )
    assert resp.status_code == 200
    assert resp.json()["recorded"] is True


def test_autopilot_host(client):
    resp = client.get("/compliance/autopilot/host")
    assert resp.status_code == 200
    assert "machine" in resp.json()


# --------------------------------------------------------------------------- #
# 32-bit legacy readiness
# --------------------------------------------------------------------------- #


def test_legacy32_assess(client):
    resp = client.get("/compliance/legacy32")
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] in {"ready", "needs_enablement"}
    assert "cpu_machine" in body["capabilities"]


def test_legacy32_plan(client):
    resp = client.post(
        "/compliance/legacy32/plan",
        json={"os_release": "ID=ubuntu\nID_LIKE=debian"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["package_manager"] == "apt"
    assert isinstance(body["steps"], list) and body["steps"]


def test_modernization_assess(client):
    resp = client.get("/modernization/assess")
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] in {"ready", "mostly_ready", "needs_modernization"}
    assert "browser_recommendation" in body


def test_modernization_playbook(client):
    resp = client.post("/modernization/playbook", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["steps"]
    assert "clock_sync" in body["apply_step_ids"]


def test_modernization_apply_requires_flag(client):
    resp = client.post("/modernization/apply", json={"allow_mutations": False})
    assert resp.status_code == 400
