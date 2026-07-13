"""DNS-over-HTTPS (DoH) resolver.

Legacy machines do plaintext DNS (UDP/53), which is unencrypted and easily
intercepted/spoofed. Alma can resolve names on their behalf over DoH (RFC 8484,
JSON variant) against a modern provider — the building block for a local DNS
forwarder that upgrades a legacy box to encrypted DNS.

Read-only and dependency-free (stdlib ``urllib``/``json``). The JSON response
parser is pure; only ``resolve_doh`` touches the network.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from alma_bridge.compliance._perf import TTLCache, network_slot

_DNS_CACHE = TTLCache()

DOH_PROVIDERS: Dict[str, str] = {
    "cloudflare": "https://cloudflare-dns.com/dns-query",
    "google": "https://dns.google/resolve",
    "quad9": "https://dns.quad9.net:5053/dns-query",
}

# Common DNS record type numbers -> names (for friendlier output).
_RECORD_TYPES = {1: "A", 2: "NS", 5: "CNAME", 6: "SOA", 15: "MX", 16: "TXT", 28: "AAAA", 257: "CAA"}
# DNS RCODE 0 == NOERROR.
_RCODE_NAMES = {0: "NOERROR", 1: "FORMERR", 2: "SERVFAIL", 3: "NXDOMAIN", 5: "REFUSED"}


def parse_doh_json(raw: Any) -> Dict[str, Any]:
    """Parse a DoH JSON (application/dns-json) response into a normal shape."""
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        try:
            obj = json.loads(raw)
        except (ValueError, TypeError):
            return {"ok": False, "status": None, "rcode": None, "answers": [], "error": "invalid DoH JSON"}
    elif isinstance(raw, dict):
        obj = raw
    else:
        return {"ok": False, "status": None, "rcode": None, "answers": [], "error": "unsupported response type"}

    if not isinstance(obj, dict):
        return {"ok": False, "status": None, "rcode": None, "answers": [], "error": "response is not an object"}

    status = obj.get("Status")
    answers: List[Dict[str, Any]] = []
    for ans in obj.get("Answer", []) or []:
        if not isinstance(ans, dict):
            continue
        rtype = ans.get("type")
        answers.append(
            {
                "name": ans.get("name"),
                "type": _RECORD_TYPES.get(rtype, rtype),
                "ttl": ans.get("TTL"),
                "data": ans.get("data"),
            }
        )
    return {
        "ok": status == 0,
        "status": status,
        "rcode": _RCODE_NAMES.get(status, status),
        "answers": answers,
        "error": None if status == 0 else _RCODE_NAMES.get(status, "DNS error"),
    }


def resolve_doh(
    name: str,
    record_type: str = "A",
    *,
    provider: str = "cloudflare",
    timeout: float = 6.0,
    cache_ttl: float = 0.0,
) -> Dict[str, Any]:
    """Resolve ``name`` over DoH against ``provider`` (cloudflare/google/quad9)."""
    base = DOH_PROVIDERS.get(provider)
    if not base:
        return {"ok": False, "status": None, "rcode": None, "answers": [], "error": f"unknown provider: {provider}"}
    cache_key = ("doh", provider, name.lower(), record_type.upper())
    hit, cached = _DNS_CACHE.get(cache_key, cache_ttl)
    if hit:
        return cached
    query = urllib.parse.urlencode({"name": name, "type": record_type})
    url = f"{base}?{query}"
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/dns-json", "User-Agent": "alma-bridge-doh/1.0"},
        method="GET",
    )
    try:
        with network_slot(), urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https only)
            body = resp.read()
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": None, "rcode": None, "answers": [], "error": f"HTTP {exc.code}"}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "status": None, "rcode": None, "answers": [], "error": str(getattr(exc, "reason", exc))}
    result = parse_doh_json(body)
    result["provider"] = provider
    result["query"] = {"name": name, "type": record_type}
    if cache_ttl > 0 and result.get("ok"):
        _DNS_CACHE.set(cache_key, result)
    return result
