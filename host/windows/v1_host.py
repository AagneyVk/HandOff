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
                        "capture": [],
                        "input": [],
                        "audio": False,
                        "media": [],
                    })
                elif msg.type == "windows.list":
                    await send(writer, "windows.snapshot", {"windows": snapshot()})
                elif msg.type == "session.start":
                    await send(writer, "error", {"code": "media_unavailable", "message": "Live capture is not implemented in this preview. Remote input is disabled."})
                elif msg.type in {"input.pointer", "input.scroll", "input.key"}:
                    raise ProtocolError("Remote input is disabled until authenticated live sessions are implemented")
                elif msg.type == "session.stop":
                    session_id = None
                    selected_window = None
                else:
                    await send(writer, "error", {"code": "unsupported", "message": msg.type}, session_id)
            except (ProtocolError, ValueError, OSError) as exc:
                LOG.warning("request from %s failed: %s", peer, exc)
                await send(writer, "error", {"code": "request_failed", "message": str(exc)}, session_id)
    except (ConnectionError, ValueError):
        LOG.info("client connection ended: %s", peer)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except ConnectionError:
            pass
        LOG.info("client disconnected: %s", peer)


def main():
    # The historical entry point now launches the authenticated desktop host.
    from host.app import main as launch
    launch()


if __name__ == "__main__":
    main()
