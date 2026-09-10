"""CI-only TLS fixture. Never imported by the production desktop entry point."""
import asyncio
from pathlib import Path
import tempfile
import sys
from host.runtime.security import Identity, TrustStore
from host.runtime.server import Host
from host.windows.window_catalog import WindowInfo
from tests.test_secure_runtime import TestCapture


async def main(path):
    with tempfile.TemporaryDirectory() as folder:
        identity = Identity(folder)
        trust = TrustStore(folder)
        host = Host(trust, lambda: [WindowInfo('win32:7', 'CI fixture', 'test', 640, 480)], lambda _: 42,
                    lambda *_: None, lambda *_: None, TestCapture)
        host.approve('win32:7')
        server = await asyncio.start_server(host.handle, '0.0.0.0', 47821, ssl=identity.context)
        # 10.0.2.2 is the emulator's route to the runner. Do not print credentials.
        Path(path).write_text(trust.invitation('10.0.2.2', 47821, identity.fingerprint))
        async with server: await server.serve_forever()


if __name__ == '__main__': asyncio.run(main(sys.argv[1]))
