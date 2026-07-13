"""TLS-modernizing bridge.

A legacy machine that can only speak plaintext or obsolete TLS can point its
traffic at a local listener managed here. For every inbound connection the
bridge opens a fresh connection to the real upstream using a *modern* TLS stack
(TLS 1.2+ and an up-to-date CA bundle) and shuttles bytes between the two. The
legacy box effectively gets today's HTTPS for free without any local changes.

This is the asyncio equivalent of ``stunnel`` in client mode, but managed
through the Bridge API so it can be started/stopped per endpoint and reported
in the compliance dashboard.
"""

from __future__ import annotations

import asyncio
import ssl
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

import certifi

_BUFFER_SIZE = 64 * 1024


@dataclass
class BridgeSpec:
    id: str
    listen_host: str
    listen_port: int
    upstream_host: str
    upstream_port: int
    verify: bool
    upstream_sni: Optional[str]
    min_tls: str
    created_at: str
    active_connections: int = 0
    total_connections: int = 0
    bytes_up: int = 0
    bytes_down: int = 0
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "listen": f"{self.listen_host}:{self.listen_port}",
            "upstream": f"{self.upstream_host}:{self.upstream_port}",
            "verify": self.verify,
            "upstream_sni": self.upstream_sni,
            "min_tls": self.min_tls,
            "created_at": self.created_at,
            "active_connections": self.active_connections,
            "total_connections": self.total_connections,
            "bytes_up": self.bytes_up,
            "bytes_down": self.bytes_down,
            "last_error": self.last_error,
        }


_MIN_TLS_MAP = {
    "TLSv1.2": ssl.TLSVersion.TLSv1_2,
    "TLSv1.3": ssl.TLSVersion.TLSv1_3,
}


class TlsModernizer:
    """Registry + lifecycle manager for TLS-modernizing bridges."""

    def __init__(self, ca_file: Optional[str] = None) -> None:
        self._ca_file = ca_file or certifi.where()
        self._specs: Dict[str, BridgeSpec] = {}
        self._servers: Dict[str, asyncio.AbstractServer] = {}

    def _make_client_context(self, verify: bool, min_tls: str) -> ssl.SSLContext:
        ctx = ssl.create_default_context(cafile=self._ca_file)
        ctx.minimum_version = _MIN_TLS_MAP.get(min_tls, ssl.TLSVersion.TLSv1_2)
        if not verify:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx

    async def start(
        self,
        upstream_host: str,
        upstream_port: int,
        *,
        listen_host: str = "127.0.0.1",
        listen_port: int = 0,
        verify: bool = True,
        upstream_sni: Optional[str] = None,
        min_tls: str = "TLSv1.2",
    ) -> BridgeSpec:
        bridge_id = uuid.uuid4().hex[:12]
        ctx = self._make_client_context(verify, min_tls)
        sni = upstream_sni or upstream_host

        spec = BridgeSpec(
            id=bridge_id,
            listen_host=listen_host,
            listen_port=listen_port,
            upstream_host=upstream_host,
            upstream_port=upstream_port,
            verify=verify,
            upstream_sni=sni,
            min_tls=min_tls,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            await self._handle_connection(spec, ctx, sni, reader, writer)

        server = await asyncio.start_server(handle, listen_host, listen_port)
        # Resolve the actual port when listen_port was 0 (ephemeral).
        sockets = server.sockets or []
        if sockets:
            spec.listen_port = sockets[0].getsockname()[1]

        self._specs[bridge_id] = spec
        self._servers[bridge_id] = server
        return spec

    async def _handle_connection(
        self,
        spec: BridgeSpec,
        ctx: ssl.SSLContext,
        sni: str,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        spec.active_connections += 1
        spec.total_connections += 1
        upstream_writer: Optional[asyncio.StreamWriter] = None
        try:
            upstream_reader, upstream_writer = await asyncio.open_connection(
                spec.upstream_host,
                spec.upstream_port,
                ssl=ctx,
                server_hostname=sni,
            )
            await asyncio.gather(
                self._pump(client_reader, upstream_writer, spec, "up"),
                self._pump(upstream_reader, client_writer, spec, "down"),
            )
        except (OSError, ssl.SSLError, asyncio.IncompleteReadError) as exc:
            spec.last_error = str(exc)
        finally:
            spec.active_connections = max(0, spec.active_connections - 1)
            for w in (upstream_writer, client_writer):
                if w is not None and not w.is_closing():
                    try:
                        w.close()
                    except OSError:
                        pass

    async def _pump(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        spec: BridgeSpec,
        direction: str,
    ) -> None:
        try:
            while True:
                chunk = await reader.read(_BUFFER_SIZE)
                if not chunk:
                    break
                writer.write(chunk)
                await writer.drain()
                if direction == "up":
                    spec.bytes_up += len(chunk)
                else:
                    spec.bytes_down += len(chunk)
        except (OSError, ssl.SSLError):
            pass
        finally:
            if not writer.is_closing():
                try:
                    if writer.can_write_eof():
                        writer.write_eof()
                except OSError:
                    pass

    async def stop(self, bridge_id: str) -> bool:
        server = self._servers.pop(bridge_id, None)
        self._specs.pop(bridge_id, None)
        if server is None:
            return False
        server.close()
        try:
            await server.wait_closed()
        except Exception:
            pass
        return True

    async def stop_all(self) -> None:
        for bridge_id in list(self._servers):
            await self.stop(bridge_id)

    def get(self, bridge_id: str) -> Optional[BridgeSpec]:
        return self._specs.get(bridge_id)

    def list(self) -> List[Dict[str, object]]:
        return [spec.to_dict() for spec in self._specs.values()]
