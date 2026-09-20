"""CI-only TLS fixture. Never imported by the production desktop entry point."""
import asyncio
from pathlib import Path
import tempfile
import sys
import math
import struct
from PIL import Image
from host.runtime.encoder import VideoEncoder
from host.runtime.security import Identity, TrustStore
from host.runtime.server import Host
from host.windows.window_catalog import WindowInfo
from tests.test_secure_runtime import TestCapture


class MediaFixture(TestCapture):
    def __init__(self, window, pid, prefer_h264=False, profile='balanced'):
        super().__init__(window, pid)
        self.encoder = VideoEncoder(prefer_h264, candidates=('libx264',), profile=profile)
    async def frame(self):
        self.frames += 1
        data, width, height, codec, backend = self.encoder.encode(Image.new('RGB', (64, 48), (20, 180, 80)))
        return data, width, height, 640, 480, codec, backend

class AudioFixture:
    async def chunk(self):
        await asyncio.sleep(.02)
        return b''.join(struct.pack('<hh', int(3000 * math.sin(i * 2 * math.pi * 440 / 48000)), 0) for i in range(960))
    def close(self): pass

async def main(path):
    with tempfile.TemporaryDirectory() as folder:
        identity = Identity(folder)
        trust = TrustStore(folder)
        host = Host(trust, lambda: [WindowInfo('win32:7', 'CI fixture', 'test', 640, 480)], lambda _: 42,
                    lambda *_: None, lambda *_: None, MediaFixture)
        host.audio_factory = AudioFixture
        host.audio_enabled = True
        host.approve('win32:7')
        server = await asyncio.start_server(host.handle, '0.0.0.0', 47821, ssl=identity.context)
        # 10.0.2.2 is the emulator's route to the runner. Do not print credentials.
        Path(path).write_text(trust.invitation('10.0.2.2', 47821, identity.fingerprint))
        async with server: await server.serve_forever()


if __name__ == '__main__': asyncio.run(main(sys.argv[1]))
