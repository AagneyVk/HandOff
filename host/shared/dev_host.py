"""Deterministic HandOff V0 development host.

Run from repository root:
    python -m host.shared.dev_host

This is intentionally not the final media transport. It proves the control loop:
hello -> capabilities -> fake window -> session -> input -> latency echo.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from .protocol import Message, ProtocolError, monotonic_us, normalized

LOG = logging.getLogger("handoff.dev_host")
HOST = "0.0.0.0"
PORT = 47820
FAKE_WINDOW = {
    "id": "fake:motion-grid",
    "title": "HandOff Motion Grid",
    "app": "handoff-dev",
    "width": 1280,
    "height": 720,
}


async def send(writer: asyncio.StreamWriter, type_: str, payload: dict, session_id=None):
    writer.write(Message(type=type_, payload=payload, session_id=session_id).encode())
    await writer.drain()


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    peer = writer.get_extra_info("peername")
    session_id: str | None = None
    LOG.info("client connected: %s", peer)
    try:
        while raw := await reader.readline():
            try:
                msg = Message.decode(raw)
                LOG.debug("%s <- %s", peer, msg.type)

                if msg.type == "hello":
                    await send(writer, "capabilities", {
                        "host_name": "HandOff V0 Dev Host",
                        "platform": "development",
                        "capture": ["deterministic-test-source"],
                        "input": ["pointer", "scroll"],
                        "audio": False,
                        "media": ["motion-grid-v0"],
                    })

                elif msg.type == "windows.list":
                    await send(writer, "windows.snapshot", {"windows": [FAKE_WINDOW]})

                elif msg.type == "session.start":
                    window_id = msg.payload.get("window_id")
                    if window_id != FAKE_WINDOW["id"]:
                        await send(writer, "error", {"code": "unknown_window", "message": str(window_id)})
                        continue
                    session_id = uuid.uuid4().hex
                    await send(writer, "session.started", {
                        "window": FAKE_WINDOW,
                        "media_mode": "motion-grid-v0",
                        "started_us": monotonic_us(),
                    }, session_id)
                    await send(writer, "stream.config", {
                        "kind": "synthetic",
                        "width": 1280,
                        "height": 720,
                        "fps": 30,
                        "description": "Client renders deterministic grid from local clock; no video bytes yet."
                    }, session_id)

                elif msg.type == "input.pointer":
                    if not session_id or msg.session_id != session_id:
                        raise ProtocolError("pointer input for inactive session")
                    x = normalized(msg.payload.get("x"), "x")
                    y = normalized(msg.payload.get("y"), "y")
                    action = msg.payload.get("action", "move")
                    LOG.info("pointer %s x=%.3f y=%.3f", action, x, y)
                    await send(writer, "telemetry.latency", {
                        "kind": "input-ack",
                        "source_message_id": msg.id,
                        "source_timestamp_us": msg.timestamp_us,
                        "host_received_us": monotonic_us(),
                    }, session_id)

                elif msg.type == "input.scroll":
                    if not session_id or msg.session_id != session_id:
                        raise ProtocolError("scroll input for inactive session")
                    LOG.info("scroll dx=%s dy=%s", msg.payload.get("dx"), msg.payload.get("dy"))
                    await send(writer, "telemetry.latency", {
                        "kind": "input-ack",
                        "source_message_id": msg.id,
                        "source_timestamp_us": msg.timestamp_us,
                        "host_received_us": monotonic_us(),
                    }, session_id)

                elif msg.type == "session.stop":
                    session_id = None

                else:
                    await send(writer, "error", {"code": "unsupported_in_harness", "message": msg.type})

            except ProtocolError as exc:
                LOG.warning("protocol error from %s: %s", peer, exc)
                await send(writer, "error", {"code": "protocol_error", "message": str(exc)})
    finally:
        writer.close()
        await writer.wait_closed()
        LOG.info("client disconnected: %s", peer)


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = await asyncio.start_server(handle, HOST, PORT)
    addresses = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    LOG.info("HandOff V0 development host listening on %s", addresses)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
