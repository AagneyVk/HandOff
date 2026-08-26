"""HandOff V0 control protocol primitives.

The control plane is deliberately transport-agnostic. Messages are newline-delimited
JSON when used by the development TCP harness, but these helpers can later sit over
another reliable transport unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import time
import uuid
from typing import Any, Mapping

PROTOCOL_VERSION = 0
ALLOWED_TYPES = {
    "hello", "capabilities", "windows.list", "windows.snapshot",
    "session.start", "session.started", "session.stop", "stream.config",
    "input.pointer", "input.scroll", "input.key", "telemetry.latency", "error",
}


class ProtocolError(ValueError):
    pass


def monotonic_us() -> int:
    return time.monotonic_ns() // 1_000


@dataclass(frozen=True)
class Message:
    type: str
    payload: Mapping[str, Any]
    id: str = ""
    session_id: str | None = None
    timestamp_us: int = 0
    version: int = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", uuid.uuid4().hex)
        if not self.timestamp_us:
            object.__setattr__(self, "timestamp_us", monotonic_us())
        validate(self)

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "version": self.version,
            "id": self.id,
            "type": self.type,
            "timestamp_us": self.timestamp_us,
            "payload": dict(self.payload),
        }
        if self.session_id is not None:
            data["session_id"] = self.session_id
        return data

    def encode(self) -> bytes:
        return (json.dumps(self.as_dict(), separators=(",", ":")) + "\n").encode()

    @classmethod
    def decode(cls, raw: bytes | str) -> "Message":
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProtocolError(f"invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ProtocolError("message must be a JSON object")
        required = {"version", "id", "type", "timestamp_us", "payload"}
        missing = required - data.keys()
        if missing:
            raise ProtocolError(f"missing fields: {sorted(missing)}")
        return cls(
            version=data["version"], id=data["id"], type=data["type"],
            session_id=data.get("session_id"), timestamp_us=data["timestamp_us"],
            payload=data["payload"],
        )


def validate(message: Message) -> None:
    if message.version != PROTOCOL_VERSION:
        raise ProtocolError(f"unsupported protocol version {message.version}")
    if message.type not in ALLOWED_TYPES:
        raise ProtocolError(f"unknown message type {message.type!r}")
    if not isinstance(message.id, str) or not message.id:
        raise ProtocolError("id must be a non-empty string")
    if not isinstance(message.timestamp_us, int) or message.timestamp_us < 0:
        raise ProtocolError("timestamp_us must be a non-negative integer")
    if not isinstance(message.payload, Mapping):
        raise ProtocolError("payload must be an object")


def normalized(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolError(f"{name} must be numeric")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise ProtocolError(f"{name} must be in range 0..1")
    return result
