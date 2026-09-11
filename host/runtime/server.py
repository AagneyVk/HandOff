import asyncio
import contextlib
import logging
import math
import secrets
import socket
import time

from . import wire
from .media import Capture
from .audio import AudioCapture, CHUNK_BYTES

LOG = logging.getLogger('handoff')


class Host:
    def __init__(self, trust, catalog, identity, pointer, scroll, capture=Capture):
        self.trust, self.catalog, self.identity = trust, catalog, identity
        self.pointer, self.scroll, self.capture_factory = pointer, scroll, capture
        self.audio_enabled = False
        self.audio_factory = AudioCapture
        self.approved = None
        self.owner = None
        self.connections = 0
        self.status = 'Choose an app to share'

    def approve(self, window):
        self.approved = (window, self.identity(window))
        self.status = 'Ready for your paired phone'

    def stop(self):
        self.approved = None
        self.status = 'Sharing stopped'

    async def handle(self, reader, writer):
        if self.connections >= 8:
            writer.close()
            return
        self.connections += 1
        client = Connection(self, reader, writer)
        try:
            await client.run()
        except (asyncio.IncompleteReadError, ConnectionError, TimeoutError, ValueError, OSError):
            pass
        except Exception:
            LOG.exception('Connection handler failed')
        finally:
            if client.watch:
                client.watch.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception): await client.watch
            await client.stop()
            self.connections -= 1
            writer.close()
            with contextlib.suppress(ConnectionError, TimeoutError):
                await asyncio.wait_for(writer.wait_closed(), 2)


class Connection:
    def __init__(self, host, reader, writer):
        self.host, self.reader, self.writer = host, reader, writer
        self.device = None
        self.session = None
        self.selection = None
        self.capture = None
        self.stream = None
        self.audio = None
        self.audio_task = None
        self.lock = asyncio.Lock()
        self.ack = asyncio.Event()
        self.sequence = 0
        self.shown_sequence = 0
        self.source_size = None
        self.watch = None
        self.input_count = 0
        self.input_since = time.monotonic()

    async def send(self, type_, **kwargs):
        async with self.lock:
            self.writer.write(wire.encode(wire.JSON, wire.message(type_, **kwargs)))
            await asyncio.wait_for(self.writer.drain(), 5)

    async def run(self):
        first = await wire.read(self.reader, 10)
        if first['type'] == 'pair':
            try:
                self.device, token = self.host.trust.pair(first.get('code'), first.get('name', 'Android'))
            except ValueError as exc:
                await self.send('error', message=str(exc))
                return
            await self.send('paired', device=self.device, token=token)
        elif first['type'] == 'auth' and self.host.trust.authenticate(first.get('device'), first.get('token')):
            self.device = first['device']
            await self.send('ready', name=socket.gethostname())
        else:
            await self.send('revoked' if first['type'] == 'auth' else 'error', message='Pair this phone again from your computer.')
            return
        self.watch = asyncio.create_task(self.watch_authorization())
        while True:
            msg = await wire.read(self.reader)
            if not self.host.trust.trusted(self.device):
                await self.send('revoked', message='This device was removed on your computer.')
                return
            try:
                await self.dispatch(msg)
            except (ValueError, OSError) as exc:
                await self.send('error', message=str(exc))

    async def watch_authorization(self):
        while True:
            await asyncio.sleep(.2)
            if self.session and (self.host.approved != self.selection or not self.host.trust.trusted(self.device)):
                await self.stop()
                await self.send('stopped', message='Sharing stopped on your computer.')

    async def dispatch(self, msg):
        type_ = msg['type']
        if type_ == 'ping':
            await self.send('pong')
        elif type_ == 'windows':
            selected = self.host.approved
            windows = [w.payload() for w in self.host.catalog() if selected and w.id == selected[0]]
            await self.send('windows', windows=windows[:1])
        elif type_ == 'start':
            if self.session:
                raise ValueError('Return the current app before starting another.')
            selection = self.host.approved
            if not selection or msg.get('window') != selection[0]:
                raise ValueError('Choose and share this app on your computer first.')
            if self.host.owner is not None:
                raise ValueError('Another phone is using this app. Return it there first.')
            if self.host.identity(selection[0]) != selection[1]:
                raise ValueError('The app changed. Share it again on your computer.')
            self.host.owner = self
            self.selection = selection
            self.session = secrets.token_hex(16)
            self.sequence = self.shown_sequence = 0
            try:
                self.capture = self.host.capture_factory(*selection, 'h264' in msg.get('codecs', []) if isinstance(msg.get('codecs', []), list) else False)
                first_frame = await self.capture.frame()
                self.validate_session()
                codec = first_frame[5] if len(first_frame) > 5 else 'jpeg'
                await self.send('started', session=self.session, codec=codec, audio=False,
                    width=first_frame[1], height=first_frame[2], encoder=first_frame[6] if len(first_frame) > 6 else 'jpeg')
                self.host.status = 'Sharing with paired phone · Stop sharing to end'
                self.stream = asyncio.create_task(self.frames(first_frame))
                if msg.get('audio') is True and self.host.audio_enabled:
                    self.audio_task = asyncio.create_task(self.audio_frames())
            except BaseException:
                await self.stop()
                raise
        elif type_ == 'stop':
            if msg.get('session') != self.session or not self.session:
                raise ValueError('Session is no longer active.')
            await self.stop()
            await self.send('stopped', message='Returned to your computer')
        elif type_ == 'ack':
            if not self.session: return
            self.validate_session(msg)
            if type(msg.get('sequence')) is int and msg['sequence'] == self.sequence:
                self.shown_sequence = self.sequence
                self.ack.set()
        elif type_ in ('tap', 'scroll'):
            self.validate_session(msg)
            if type(msg.get('sequence')) is not int or msg['sequence'] != self.shown_sequence or msg['sequence'] != self.sequence or not self.shown_sequence:
                raise ValueError('Wait for the current frame before controlling the app.')
            now = time.monotonic()
            if now - self.input_since > 1:
                self.input_since, self.input_count = now, 0
            self.input_count += 1
            if self.input_count > 60:
                raise ValueError('Too many input events.')
            x, y = self.number(msg.get('x'), 0, 1), self.number(msg.get('y'), 0, 1)
            if type_ == 'tap':
                self.host.pointer(self.selection[0], x, y, self.source_size)
            else:
                dy = self.number(msg.get('dy'), -10, 10)
                self.host.scroll(self.selection[0], x, y, dy, self.source_size)
        else:
            raise ValueError('Unsupported request')

    @staticmethod
    def number(value, low, high):
        if type(value) not in (float, int) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError('Invalid input coordinates')
        return float(value)

    def validate_session(self, msg=None):
        if (not self.session or self.host.approved != self.selection or not self.host.trust.trusted(self.device)
                or (msg is not None and msg.get('session') != self.session)):
            raise ValueError('Sharing ended on your computer.')
        if self.host.identity(self.selection[0]) != self.selection[1]:
            raise ValueError('The selected app closed or changed.')

    async def frames(self, frame):
        try:
            while True:
                started = time.monotonic()
                self.validate_session()
                data, width, height, sw, sh, *codec_info = frame
                codec = codec_info[0] if codec_info else 'jpeg'
                self.source_size = (sw, sh)
                self.sequence += 1
                self.ack.clear()
                async with self.lock:
                    self.writer.write(wire.encode(wire.JSON, wire.message('frame', session=self.session,
                        sequence=self.sequence, width=width, height=height, codec=codec)))
                    self.writer.write(wire.encode(wire.H264 if codec == 'h264' else wire.JPEG, data))
                    await asyncio.wait_for(self.writer.drain(), 5)
                # No second frame may accumulate while Android is decoding/displaying this one.
                await asyncio.wait_for(self.ack.wait(), 10)
                await asyncio.sleep(max(0, 1 / (30 if codec == 'h264' else 12) - (time.monotonic() - started)))
                frame = await self.capture.frame()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            with contextlib.suppress(Exception):
                await self.send('stopped', message=str(exc) or 'Stream timed out. Reconnect to continue.')
        finally:
            self.release()

    async def audio_frames(self):
        try:
            self.audio = self.host.audio_factory()
            while self.session and self.host.audio_enabled:
                chunk = await self.audio.chunk()
                self.validate_session()
                if not self.host.audio_enabled: break
                if len(chunk) != CHUNK_BYTES: raise ValueError('Invalid PCM chunk')
                async with self.lock:
                    self.writer.write(wire.encode(wire.JSON, wire.message('audio', session=self.session,
                        rate=48000, channels=2, format='s16le')))
                    self.writer.write(wire.encode(wire.PCM, chunk))
                    await asyncio.wait_for(self.writer.drain(), 1)
            if self.session:
                await self.send('audio.stopped', message='Audio disabled on your computer.')
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            with contextlib.suppress(Exception): await self.send('audio.stopped', message=str(exc))
        finally:
            if self.audio: self.audio.close(); self.audio = None

    def release(self):
        if self.capture:
            self.capture.close()
            self.capture = None
        self.session = None
        if self.audio_task: self.audio_task.cancel()
        if self.host.owner is self:
            self.host.owner = None
            self.host.status = 'Ready for your paired phone' if self.host.approved else 'Sharing stopped'

    async def stop(self):
        if self.audio_task:
            self.audio_task.cancel()
            with contextlib.suppress(asyncio.CancelledError): await self.audio_task
            self.audio_task = None
        if self.stream:
            self.stream.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.stream
            self.stream = None
        self.release()
