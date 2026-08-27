"""HandOff V1 Windows control host.

This is the first host that exposes real top-level Windows windows and routes an
active session's normalized Android pointer/scroll events into that exact HWND.
Media remains a separately negotiated capability until the native capture bridge lands.
"""
from __future__ import annotations

import asyncio
import logging
import socket
import uuid

from host.shared.protocol import Message, ProtocolError, monotonic_us, normalized
from host.windows.input_backend import scroll, tap
from host.windows.window_catalog import list_windows

LOG = logging.getLogger("handoff.windows")
HOST = "0.0.0.0"
PORT = 47820


def host_name() -> str:
    return socket.gethostname() or "Windows PC"


def snapshot() -> list[dict]:
    return [window.payload() for window in list_windows()]


async def send(writer: asyncio.StreamWriter, type_: str, payload: dict, session_id: str | None = None):
    writer.write(Message(type=type_, payload=payload, session_id=session_id).encode())
    await writer.drain()


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    peer = writer.get_extra_info("peername")
    session_id: str | None = None
    selected_window: str | None = None
    LOG.info("client connected: %s", peer)
    try:
        while raw := await reader.readline():
            try:
                msg = Message.decode(raw)
                if msg.type == "hello":
                    await send(writer, "capabilities", {
                        "host_name": host_name(),
                        "platform": "windows",
                        "capture": ["windows-graphics-capture-planned"],
                        "input": ["pointer", "scroll"],
                        "audio": False,
                        "media": [],
                    })
                elif msg.type == "windows.list":
                    await send(writer, "windows.snapshot", {"windows": snapshot()})
                elif msg.type == "session.start":
                    requested = str(msg.payload.get("window_id", ""))
                    windows = {item["id"]: item for item in snapshot()}
                    if requested not in windows:
                        await send(writer, "error", {"code": "unknown_window", "message": "That window is no longer available."})
                        continue
                    session_id = uuid.uuid4().hex
                    selected_window = requested
                    await send(writer, "session.started", {
                        "window": windows[requested],
                        "media_mode": "control-only-v1",
                        "started_us": monotonic_us(),
                    }, session_id)
                elif msg.type == "input.pointer":
                    if not session_id or msg.session_id != session_id or not selected_window:
                        raise ProtocolError("pointer input for inactive session")
                    action = msg.payload.get("action", "tap")
                    if action != "tap":
                        raise ProtocolError(f"unsupported pointer action {action!r}")
                    tap(selected_window, normalized(msg.payload.get("x"), "x"), normalized(msg.payload.get("y"), "y"))
                    await send(writer, "telemetry.latency", {"kind": "input-ack", "source_message_id": msg.id, "source_timestamp_us": msg.timestamp_us, "host_received_us": monotonic_us()}, session_id)
                elif msg.type == "input.scroll":
                    if not session_id or msg.session_id != session_id or not selected_window:
                        raise ProtocolError("scroll input for inactive session")
                    # Until the Android content transform sends pointer position with scroll,
                    # place wheel input at the centre of the selected window.
                    dy = float(msg.payload.get("dy", 0.0))
                    scroll(selected_window, .5, .5, dy)
                    await send(writer, "telemetry.latency", {"kind": "input-ack", "source_message_id": msg.id, "source_timestamp_us": msg.timestamp_us, "host_received_us": monotonic_us()}, session_id)
                elif msg.type == "session.stop":
                    session_id = None
                    selected_window = None
                else:
                    await send(writer, "error", {"code": "unsupported", "message": msg.type}, session_id)
            except (ProtocolError, ValueError, OSError) as exc:
                LOG.warning("request from %s failed: %s", peer, exc)
                await send(writer, "error", {"code": "request_failed", "message": str(exc)}, session_id)
    finally:
        writer.close()
        await writer.wait_closed()
        LOG.info("client disconnected: %s", peer)


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = await asyncio.start_server(handle, HOST, PORT)
    LOG.info("HandOff V1 Windows host %s listening on port %d", host_name(), PORT)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
