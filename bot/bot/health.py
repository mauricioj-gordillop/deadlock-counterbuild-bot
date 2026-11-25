"""Zero-dependency async HTTP /health server running inside the Discord bot process."""

from __future__ import annotations

import asyncio
import json

from bot.store import CounterStore


class HealthServer:
    """Minimal asyncio HTTP server exposing GET /health for container healthchecks."""

    def __init__(self, store: CounterStore, host: str = "0.0.0.0", port: int = 8080) -> None:
        self._store = store
        self._host = host
        self._port = port
        self._server: asyncio.AbstractServer | None = None

    @property
    def bound_port(self) -> int | None:
        if self._server and self._server.sockets:
            return int(self._server.sockets[0].getsockname()[1])
        return None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_client, self._host, self._port)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=2.0)
            parts = request_line.decode("latin-1", errors="replace").strip().split()
            path = parts[1] if len(parts) >= 2 else "/"

            if path.split("?", 1)[0] not in ("/health", "/"):
                status_line = "HTTP/1.1 404 Not Found"
                body_bytes = b'{"status":"not_found"}'
            else:
                ready, summary = self._store.health_summary()
                status_line = (
                    "HTTP/1.1 200 OK" if ready else "HTTP/1.1 503 Service Unavailable"
                )
                body_bytes = json.dumps(summary).encode("utf-8")

            headers = (
                f"{status_line}\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body_bytes)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
            writer.write(headers + body_bytes)
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
