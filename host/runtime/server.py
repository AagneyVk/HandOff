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
    def __init__(self, trust, catalog, identity, pointer, scroll, capture=Capture,
                 drag=None, text=None, key=None):
        self.trust, self.catalog, self.identity = trust, catalog, identity
        self.pointer, self.scroll, self.capture_factory = pointer, scroll, capture
        self.drag, self.text, self.key = drag, text, key
        self.audio_enabled = False
        self.audio_factory = AudioCapture
        self.approved = None
        self.owner = None
        self.phone_owner = None
        self.phone_presenter = None
        self.connections = 0
        self.status = 'Choose an app or display to share'

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
        self.profile = 'balanced'
        self.source_session = None
        self.source_sequence = 0
        self.source_controls = False

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
                self.profile = msg.get('profile', 'balanced')
                if self.profile not in ('smooth', 'balanced', 'sharp'):
                    raise ValueError('Unsupported stream profile.')
                self.capture = self.host.capture_factory(*selection,
                    'h264' in msg.get('codecs', []) if isinstance(msg.get('codecs', []), list) else False,
                    self.profile)
                first_frame = await self.capture.frame()
                self.validate_session()
                codec = first_frame[5] if len(first_frame) > 5 else 'jpeg'
                controls = ['tap', 'scroll'] + (['drag'] if self.host.drag else [])
                if self.host.text and self.host.key: controls += ['text', 'key']
                fps = {'smooth': 30, 'balanced': 30, 'sharp': 24}[self.profile]
                await self.send('started', session=self.session, codec=codec, controls=controls,
                    profile=self.profile, fps=fps,
                    target='display' if self.selection[0].startswith(('display:', 'xdisplay:')) else 'window',
                    audio=msg.get('audio') is True and self.host.audio_enabled,
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
        elif type_ == 'drag':
            self.validate_control(msg)
            if self.host.drag is None: raise ValueError('Drag control is unavailable on this computer.')
            x0, y0 = self.number(msg.get('x0'), 0, 1), self.number(msg.get('y0'), 0, 1)
            x1, y1 = self.number(msg.get('x1'), 0, 1), self.number(msg.get('y1'), 0, 1)
            self.host.drag(self.selection[0], x0, y0, x1, y1, self.source_size)
        elif type_ == 'text':
            self.validate_control(msg)
            if self.host.text is None: raise ValueError('Remote typing is unavailable on this computer.')
            value = msg.get('text')
            if not isinstance(value, str) or not 1 <= len(value) <= 256:
                raise ValueError('Text must contain 1 to 256 characters.')
            self.host.text(self.selection[0], value, self.source_size)
        elif type_ == 'key':
            self.validate_control(msg)
            if self.host.key is None: raise ValueError('Remote keys are unavailable on this computer.')
            name = msg.get('key')
            if name not in ('backspace', 'tab', 'enter', 'escape', 'left', 'up', 'right', 'down', 'delete'):
                raise ValueError('Unsupported key.')
            self.host.key(self.selection[0], name, self.source_size)
        elif type_ == 'source.start':
            if self.session or self.source_session: raise ValueError('Another HandOff session is already active.')
            if self.host.phone_owner is not None: raise ValueError('Another phone screen is already shared.')
            width, height = msg.get('width'), msg.get('height')
            if (type(width) is not int or type(height) is not int or not (2 <= width <= 1920 and 2 <= height <= 1920)
                    or width * height > 1920 * 1080):
                raise ValueError('Unsupported phone video dimensions.')
            if msg.get('codec') != 'h264': raise ValueError('Phone sharing requires H.264.')
            self.source_session, self.source_sequence = secrets.token_hex(16), 0
            self.source_controls = msg.get('controls') is True
            self.host.phone_owner = self
            try:
                if self.host.phone_presenter is None: raise ValueError('Phone presentation is unavailable.')
                self.host.phone_presenter.start(self, width, height, msg.get('audio') is True, self.source_controls)
                self.host.status = 'Phone is live on this computer · Close its viewer to return'
                await self.send('source.ready', session=self.source_session)
            except BaseException:
                self.stop_source(); raise
        elif type_ == 'source.frame':
            self.validate_source(msg)
            sequence = msg.get('sequence')
            if type(sequence) is not int or sequence != self.source_sequence + 1:
                raise ValueError('Out-of-order phone frame.')
            data = await wire.read_binary(self.reader, wire.H264, 5)
            if not self.host.phone_presenter.feed_video(data):
                raise ValueError('Phone video did not decode.')
            self.source_sequence = sequence
            await self.send('source.ack', session=self.source_session, sequence=sequence)
        elif type_ == 'source.audio':
            self.validate_source(msg)
            if msg.get('rate') != 48000 or msg.get('channels') != 2 or msg.get('format') != 's16le':
                raise ValueError('Unsupported phone audio format.')
            data = await wire.read_binary(self.reader, wire.PCM, 2)
            if len(data) != CHUNK_BYTES: raise ValueError('Invalid phone audio packet.')
            self.host.phone_presenter.feed_audio(data)
        elif type_ == 'source.stop':
            self.validate_source(msg)
            self.stop_source()
            await self.send('source.stopped', message='Phone returned')
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

    def validate_control(self, msg):
        self.validate_session(msg)
        if type(msg.get('sequence')) is not int or msg['sequence'] != self.shown_sequence or msg['sequence'] != self.sequence or not self.shown_sequence:
            raise ValueError('Wait for the current frame before controlling the app.')
        now = time.monotonic()
        if now - self.input_since > 1: self.input_since, self.input_count = now, 0
        self.input_count += 1
        if self.input_count > 60: raise ValueError('Too many input events.')

    def validate_source(self, msg):
        if (not self.source_session or self.host.phone_owner is not self
                or msg.get('session') != self.source_session or not self.host.trust.trusted(self.device)):
            raise ValueError('Phone sharing session ended.')

    def stop_source(self):
        if self.host.phone_presenter: self.host.phone_presenter.stop(self)
        self.source_session = None
        self.source_controls = False
        if self.host.phone_owner is self:
            self.host.phone_owner = None
            self.host.status = 'Ready for your paired phone' if self.host.approved else 'Choose an app or display to share'

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
                requested = {'smooth': 30, 'balanced': 30, 'sharp': 24}[self.profile]
                await asyncio.sleep(max(0, 1 / (requested if codec == 'h264' else min(12, requested)) - (time.monotonic() - started)))
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
        self.stop_source()
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
