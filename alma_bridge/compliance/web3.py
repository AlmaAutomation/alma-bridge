"""Web3 compliance for legacy hosts.

Legacy machines struggle with the decentralized web for the same reasons they
struggle with modern HTTPS — and a few extra ones:

* EVM JSON-RPC providers are HTTPS-only with modern TLS (handled by the TLS
  assessor / modernizing bridge in this package).
* dApps reference content via ``ipfs://`` / ``ipns://`` URIs that an old
  browser can't resolve.
* Wallets/clients need to know the chain id of the endpoint they're talking to.

This module provides, dependency-free (stdlib ``urllib`` + ``json``):

* a chain-id registry,
* pure JSON-RPC request/response helpers,
* IPFS/IPNS URI -> gateway URL rewriting and CID sanity checks,
* a live read-only RPC probe (``eth_chainId`` / ``web3_clientVersion``),
* a readiness verdict that folds in the endpoint's TLS posture.

Everything network-facing is isolated in ``probe_*`` functions; the verdict
logic is pure and unit-testable.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from alma_bridge.compliance._perf import TTLCache, network_slot
from alma_bridge.compliance.tls import assess_tls

_WEB3_CACHE = TTLCache()

# Common EVM chains (EIP-155). Not exhaustive; unknown ids degrade gracefully.
CHAIN_REGISTRY: Dict[int, Dict[str, str]] = {
    1: {"name": "Ethereum Mainnet", "currency": "ETH"},
    10: {"name": "OP Mainnet", "currency": "ETH"},
    56: {"name": "BNB Smart Chain", "currency": "BNB"},
    100: {"name": "Gnosis", "currency": "xDAI"},
    137: {"name": "Polygon", "currency": "POL"},
    250: {"name": "Fantom Opera", "currency": "FTM"},
    324: {"name": "zkSync Era", "currency": "ETH"},
    8453: {"name": "Base", "currency": "ETH"},
    17000: {"name": "Holesky", "currency": "ETH"},
    42161: {"name": "Arbitrum One", "currency": "ETH"},
    43114: {"name": "Avalanche C-Chain", "currency": "AVAX"},
    59144: {"name": "Linea", "currency": "ETH"},
    534352: {"name": "Scroll", "currency": "ETH"},
    11155111: {"name": "Sepolia", "currency": "ETH"},
    80002: {"name": "Polygon Amoy", "currency": "POL"},
}

DEFAULT_IPFS_GATEWAY = "https://ipfs.io"
_BASE58_ALPHABET = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
_BASE32_CID_ALPHABET = set("abcdefghijklmnopqrstuvwxyz234567")


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #


def build_jsonrpc_request(method: str, params: Optional[List[Any]] = None, req_id: int = 1) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or []}


def parse_jsonrpc_response(raw: Any) -> Dict[str, Any]:
    """Parse a JSON-RPC response body into ``{ok, result, error}``."""
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        try:
            obj = json.loads(raw)
        except (ValueError, TypeError):
            return {"ok": False, "result": None, "error": "invalid JSON-RPC response"}
    elif isinstance(raw, dict):
        obj = raw
    else:
        return {"ok": False, "result": None, "error": "unsupported response type"}

    if not isinstance(obj, dict):
        return {"ok": False, "result": None, "error": "response is not a JSON object"}
    if obj.get("error") is not None:
        err = obj["error"]
        message = err.get("message") if isinstance(err, dict) else str(err)
        return {"ok": False, "result": None, "error": message or "RPC error"}
    if "result" not in obj:
        return {"ok": False, "result": None, "error": "no result field"}
    return {"ok": True, "result": obj["result"], "error": None}


def decode_quantity(value: Any) -> Optional[int]:
    """Decode an Ethereum hex quantity (e.g. ``0x1``) into an int."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    try:
        if text.lower().startswith("0x"):
            return int(text, 16)
        return int(text)
    except ValueError:
        return None


def chain_info(chain_id: Optional[int]) -> Dict[str, Any]:
    if chain_id is None:
        return {"chain_id": None, "name": "unknown", "currency": None, "known": False}
    entry = CHAIN_REGISTRY.get(chain_id)
    return {
        "chain_id": chain_id,
        "name": entry["name"] if entry else f"chain {chain_id}",
        "currency": entry["currency"] if entry else None,
        "known": entry is not None,
    }


def is_valid_cid(cid: str) -> bool:
    """Heuristic CID validation (CIDv0 base58btc, CIDv1 base32)."""
    if not cid or not isinstance(cid, str):
        return False
    cid = cid.strip()
    if cid.startswith("Qm") and len(cid) == 46:
        return all(c in _BASE58_ALPHABET for c in cid)
    if cid.startswith("b") and len(cid) >= 10:
        return all(c in _BASE32_CID_ALPHABET for c in cid[1:].lower())
    return False


def normalize_ipfs_uri(uri: str, gateway: str = DEFAULT_IPFS_GATEWAY) -> Dict[str, Any]:
    """Rewrite ``ipfs://`` / ``ipns://`` URIs to an HTTPS gateway URL.

    Returns ``{url, scheme, cid, valid_cid}``. http(s) URIs pass through.
    """
    gateway = gateway.rstrip("/")
    if not uri or not isinstance(uri, str):
        return {"url": None, "scheme": None, "cid": None, "valid_cid": False, "error": "empty uri"}

    text = uri.strip()
    lowered = text.lower()
    if lowered.startswith(("http://", "https://")):
        return {"url": text, "scheme": "http", "cid": None, "valid_cid": True}

    for scheme in ("ipfs", "ipns"):
        prefix = f"{scheme}://"
        if lowered.startswith(prefix):
            remainder = text[len(prefix):]
            # Some URIs use ipfs://ipfs/<cid>; strip a redundant leading segment.
            if remainder.lower().startswith(f"{scheme}/"):
                remainder = remainder[len(scheme) + 1:]
            cid, _, path = remainder.partition("/")
            url = f"{gateway}/{scheme}/{remainder}"
            valid = is_valid_cid(cid) if scheme == "ipfs" else bool(cid)
            return {"url": url, "scheme": scheme, "cid": cid, "valid_cid": valid}

    return {"url": None, "scheme": None, "cid": None, "valid_cid": False, "error": "unsupported scheme"}


def evaluate_web3_posture(
    observation: Dict[str, Any], tls_verdict: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Pure verdict: is this endpoint usable as a modern web3 provider?"""
    blockers: List[str] = []
    warnings: List[str] = []

    if not observation.get("reachable"):
        blockers.append(observation.get("error") or "RPC endpoint unreachable")

    chain_id = observation.get("chain_id")
    if observation.get("reachable") and chain_id is None:
        blockers.append("endpoint did not return a valid chain id (eth_chainId)")

    info = chain_info(chain_id)
    if chain_id is not None and not info["known"]:
        warnings.append(f"unrecognized chain id {chain_id}")

    if tls_verdict is not None and not tls_verdict.get("compliant"):
        blockers.append(
            "RPC endpoint TLS is not modern: "
            + ("; ".join(tls_verdict.get("blockers", [])) or "see TLS report")
        )

    ready = not blockers
    recommendation = None
    if not ready and tls_verdict is not None and not tls_verdict.get("compliant"):
        recommendation = (
            "Front the RPC endpoint with an Alma TLS-modernizing bridge so legacy "
            "wallets/clients can reach it over modern TLS."
        )
    elif not ready:
        recommendation = "Verify the RPC URL and that the provider is reachable."

    return {
        "web3_ready": ready,
        "chain": info,
        "client_version": observation.get("client_version"),
        "latency_ms": observation.get("latency_ms"),
        "blockers": blockers,
        "warnings": warnings,
        "recommendation": recommendation,
        "tls": tls_verdict,
        "observation": observation,
    }


# --------------------------------------------------------------------------- #
# Live probes
# --------------------------------------------------------------------------- #


def _rpc_call(url: str, method: str, timeout: float) -> Dict[str, Any]:
    payload = json.dumps(build_jsonrpc_request(method)).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "alma-bridge-web3/1.0"},
        method="POST",
    )
    with network_slot(), urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (validated below)
        body = resp.read()
    return parse_jsonrpc_response(body)


def _split_host_port(url: str) -> Tuple[Optional[str], int, str]:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    port = parsed.port or (443 if scheme == "https" else 80)
    return parsed.hostname, port, scheme


def probe_jsonrpc(url: str, *, timeout: float = 8.0) -> Dict[str, Any]:
    """Read-only liveness probe of an EVM JSON-RPC endpoint."""
    observation: Dict[str, Any] = {
        "url": url,
        "reachable": False,
        "chain_id": None,
        "client_version": None,
        "latency_ms": None,
        "error": None,
    }
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https"):
        observation["error"] = f"unsupported scheme: {parsed.scheme or 'none'}"
        return observation

    started = time.perf_counter()
    try:
        chain = _rpc_call(url, "eth_chainId", timeout)
        observation["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        if chain["ok"]:
            observation["reachable"] = True
            observation["chain_id"] = decode_quantity(chain["result"])
        else:
            observation["error"] = chain["error"]
            # Some endpoints disable eth_chainId; net_version is a fallback.
            net = _rpc_call(url, "net_version", timeout)
            if net["ok"]:
                observation["reachable"] = True
                observation["chain_id"] = decode_quantity(net["result"])
                observation["error"] = None
    except urllib.error.HTTPError as exc:
        observation["error"] = f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        observation["error"] = str(getattr(exc, "reason", exc))
        return observation

    if observation["reachable"]:
        try:
            client = _rpc_call(url, "web3_clientVersion", timeout)
            if client["ok"]:
                observation["client_version"] = client["result"]
        except (urllib.error.URLError, OSError, ValueError):
            pass
    return observation


def assess_web3_endpoint(
    url: str, *, timeout: float = 8.0, check_tls: bool = True, cache_ttl: float = 0.0
) -> Dict[str, Any]:
    """Probe an RPC endpoint and return a web3-readiness verdict."""

    def _compute() -> Dict[str, Any]:
        observation = probe_jsonrpc(url, timeout=timeout)
        tls_verdict = None
        host, port, scheme = _split_host_port(url)
        if check_tls and scheme == "https" and host:
            # Share the TLS cache so a host probed as both target and RPC is
            # only handshaked once.
            tls_verdict = assess_tls(
                host, port, timeout=timeout, probe_legacy=False, cache_ttl=cache_ttl
            )
        verdict = evaluate_web3_posture(observation, tls_verdict)
        verdict["url"] = url
        return verdict

    return _WEB3_CACHE.get_or_compute(("web3", url, check_tls), cache_ttl, _compute)
