"""V1 wire: big-endian uint32 length, byte kind, payload. TLS is mandatory.

Kind 1 is UTF-8 JSON, kind 2 is JPEG. No packet exceeds 2 MiB.
"""
import asyncio
import json
import struct

MAX_CONTROL = 16384
MAX_PACKET = 2 * 1024 * 1024
JSON = 1
JPEG = 2


def encode(kind, payload):
    if kind == JSON:
        payload = json.dumps(payload, allow_nan=False, separators=(',', ':')).encode()
        if len(payload) > MAX_CONTROL:
            raise ValueError('Control message too large')
    if kind not in (JSON, JPEG) or not 0 < len(payload) < MAX_PACKET:
        raise ValueError('Invalid packet')
    return struct.pack('!IB', len(payload) + 1, kind) + payload


async def read(reader, timeout=30):
    async def receive():
        size = struct.unpack('!I', await reader.readexactly(4))[0]
        if not 1 < size <= MAX_CONTROL + 1:
            raise ValueError('Invalid control packet size')
        data = await reader.readexactly(size)
        if data[0] != JSON:
            raise ValueError('Expected control message')
        obj = json.loads(data[1:], parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite number')))
        if not isinstance(obj, dict) or obj.get('v') != 1 or type(obj.get('v')) is not int or not isinstance(obj.get('type'), str):
            raise ValueError('Unsupported control envelope')
        return obj
    return await asyncio.wait_for(receive(), timeout)


def message(type_, **kwargs):
    return dict(v=1, type=type_, **kwargs)
