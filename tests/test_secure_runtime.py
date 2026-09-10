import asyncio
import io
import json
import ssl
import struct
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import Mock, patch

from PIL import Image
from host.runtime import wire
from host.runtime.security import Identity, TrustStore
from host.runtime.server import Host
from host.windows.window_catalog import WindowInfo


class SecurityTests(unittest.TestCase):
    def test_identity_persists_and_invites_expire_and_cannot_be_replayed(self):
        with tempfile.TemporaryDirectory() as folder:
            identity = Identity(folder)
            self.assertEqual(identity.fingerprint, Identity(folder).fingerprint)
            store = TrustStore(folder)
            link = store.invitation('127.0.0.1', 47821, identity.fingerprint)
            code = parse_qs(urlparse(link).query)['code'][0]
            device, token = store.pair(code, 'Phone')
            self.assertTrue(TrustStore(folder).authenticate(device, token))
            self.assertFalse(store.authenticate(device, 'wrong'))
            self.assertNotIn(token, store.path.read_text())
            with self.assertRaises(ValueError): store.pair(code, 'Replay')
            store.invitation('127.0.0.1', 47821, identity.fingerprint)
            store.expires = 0
            with self.assertRaises(ValueError): store.pair(store.invite, 'Late')
            store.revoke_all()
            self.assertFalse(store.authenticate(device, token))


class TestCapture:
    instances = []
    def __init__(self, *_):
        self.frames = 0
        self.closed = False
        self.__class__.instances.append(self)
    async def frame(self):
        self.frames += 1
        image = Image.new('RGB', (64, 48), (20, 180, 80))
        data = io.BytesIO(); image.save(data, 'JPEG')
        return data.getvalue(), 64, 48, 640, 480
    def close(self): self.closed = True


class SecureRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.identity = Identity(self.folder.name)
        self.trust = TrustStore(self.folder.name)
        self.code = parse_qs(urlparse(self.trust.invitation('127.0.0.1', 47821, self.identity.fingerprint)).query)['code'][0]
        self.pointer = Mock()
        self.host = Host(self.trust, lambda: [WindowInfo('win32:7', 'Test app', 'test', 640, 480)], lambda _: 42, self.pointer, Mock(), TestCapture)
        self.server = await asyncio.start_server(self.host.handle, '127.0.0.1', 0, ssl=self.identity.context)
        # Trust exactly this generated certificate; hostname is deliberately not the trust identity.
        self.context = ssl.create_default_context(cafile=str(self.identity.pem))
        self.context.check_hostname = False
        self.connections = []
        self.reader, self.writer = await self.connect()

    async def connect(self):
        pair = await asyncio.open_connection('127.0.0.1', self.server.sockets[0].getsockname()[1], ssl=self.context)
        self.connections.append(pair)
        return pair

    async def asyncTearDown(self):
        for _, writer in self.connections: writer.close()
        for _, writer in self.connections:
            try: await writer.wait_closed()
            except (ConnectionError, OSError): pass
        self.server.close(); await self.server.wait_closed()
        for _ in range(30):
            if self.host.connections == 0: break
            await asyncio.sleep(.01)
        self.folder.cleanup()

    async def send(self, type_, **kwargs):
        self.writer.write(wire.encode(wire.JSON, wire.message(type_, **kwargs)))
        await self.writer.drain()

    async def receive(self):
        size = struct.unpack('!I', await asyncio.wait_for(self.reader.readexactly(4), 2))[0]
        packet = await self.reader.readexactly(size)
        return json.loads(packet[1:]) if packet[0] == 1 else packet[1:]

    async def pair(self):
        await self.send('pair', code=self.code, name='Test phone')
        paired = await self.receive()
        self.assertEqual(paired['type'], 'paired')
        return paired

    async def start(self):
        self.host.approve('win32:7')
        await self.send('start', window='win32:7')
        started = await self.receive()
        self.assertEqual(started['type'], 'started')
        meta, jpeg = await self.receive(), await self.receive()
        self.assertEqual(meta['type'], 'frame')
        with Image.open(io.BytesIO(jpeg)) as image:
            self.assertEqual(image.size, (64, 48))
            self.assertGreater(image.getpixel((20, 20))[1], 170)
        return started['session'], meta['sequence']

    async def test_pair_stream_backpressure_input_stop_and_restart(self):
        await self.pair()
        session, sequence = await self.start()
        capture = TestCapture.instances[-1]
        await asyncio.sleep(.15)
        self.assertEqual(capture.frames, 1, 'Capture must wait for the displayed-frame acknowledgement')
        await self.send('ack', session=session, sequence=sequence)
        await self.send('tap', session=session, sequence=sequence, x=.25, y=.75)
        await self.send('stop', session=session)
        self.assertEqual((await self.receive())['type'], 'stopped')
        self.pointer.assert_called_once_with('win32:7', .25, .75, (640, 480))
        self.assertTrue(capture.closed)
        self.assertIsNone(self.host.owner)
        new_session, _ = await self.start()
        self.assertNotEqual(new_session, session)

    async def test_reject_unapproved_app_and_stale_session(self):
        await self.pair()
        await self.send('windows')
        self.assertEqual((await self.receive())['windows'], [])
        await self.send('start', window='win32:7')
        self.assertEqual((await self.receive())['type'], 'error')
        session, seq = await self.start()
        await self.send('tap', session='stale', sequence=seq, x=.5, y=.5)
        self.assertEqual((await self.receive())['type'], 'error')
        self.pointer.assert_not_called()
        await self.send('stop', session=session)
        self.assertEqual((await self.receive())['type'], 'stopped')

    async def test_revocation_blocks_next_message_and_releases_capture(self):
        await self.pair()
        await self.start()
        self.trust.revoke_all()
        await self.send('ping')
        self.assertEqual((await self.receive())['type'], 'revoked')
        self.assertEqual(await self.reader.read(), b'')
        self.assertTrue(TestCapture.instances[-1].closed)

    async def test_auth_required_before_window_titles(self):
        await self.send('windows')
        self.assertEqual((await self.receive())['type'], 'error')
        self.assertEqual(await self.reader.read(), b'')

    async def test_reconnect_with_credential(self):
        paired = await self.pair()
        self.writer.close(); await self.writer.wait_closed()
        self.reader, self.writer = await self.connect()
        await self.send('auth', device=paired['device'], token=paired['token'])
        self.assertEqual((await self.receive())['type'], 'ready')

    async def test_oversize_packet_closes_without_allocating_payload(self):
        self.writer.write(struct.pack('!I', 0x7FFFFFFF)); await self.writer.drain()
        self.assertEqual(await asyncio.wait_for(self.reader.read(), 2), b'')

    async def test_untrusted_tls_certificate_is_rejected(self):
        with self.assertRaises(ssl.SSLCertVerificationError):
            await asyncio.open_connection('127.0.0.1', self.server.sockets[0].getsockname()[1], ssl=ssl.create_default_context())

    async def test_capture_failure_releases_session_owner(self):
        await self.pair()
        self.host.approve('win32:7')
        class Broken(TestCapture):
            async def frame(self): raise ValueError('Capture failed')
        self.host.capture_factory = Broken
        await self.send('start', window='win32:7')
        self.assertEqual((await self.receive())['type'], 'error')
        self.assertIsNone(self.host.owner)

    async def test_input_validation(self):
        from host.runtime.server import Connection
        for value in [True, None, float('nan'), float('inf'), [], '0.5', -1, 2]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError): Connection.number(value, 0, 1)
