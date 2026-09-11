"""Probe a real encoded frame before advertising a hardware codec."""
from fractions import Fraction
import io


class VideoEncoder:
    def __init__(self, prefer_h264=False, candidates=None):
        self.prefer_h264 = prefer_h264
        self.candidates = candidates if candidates is not None else ('h264_nvenc', 'h264_qsv', 'h264_amf')
        self.context = None
        self.size = None
        self.backend = 'jpeg'
        self.codec = 'jpeg'
        self.index = 0
        self.probed = False

    def _open(self, name, size):
        import av
        ctx = av.CodecContext.create(name, 'w')
        ctx.width, ctx.height = size
        ctx.time_base = Fraction(1, 30)
        ctx.framerate = Fraction(30, 1)
        ctx.pix_fmt = 'nv12' if name in ('h264_qsv', 'h264_amf') else 'yuv420p'
        ctx.bit_rate = 4_000_000
        ctx.gop_size = 30
        ctx.max_b_frames = 0
        options = {
            'h264_nvenc': {'preset': 'p1', 'tune': 'ull', 'zerolatency': '1', 'delay': '0'},
            'h264_qsv': {'preset': 'veryfast', 'async_depth': '1', 'look_ahead': '0'},
            'h264_amf': {'usage': 'ultralowlatency', 'quality': 'speed'},
            'libx264': {'preset': 'ultrafast', 'tune': 'zerolatency', 'x264-params': 'repeat-headers=1:annexb=1'},
        }
        ctx.options = options.get(name, {})
        ctx.open()
        return ctx

    def _encode(self, context, image):
        import av
        frame = av.VideoFrame.from_image(image).reformat(format=context.pix_fmt)
        frame.pts = self.index
        frame.time_base = Fraction(1, 30)
        packets = context.encode(frame)
        data = b''.join(bytes(packet) for packet in packets)
        # Frame pacing needs immediate access units, not delayed/B-frame encoders.
        if not data or not data.startswith((b'\x00\x00\x01', b'\x00\x00\x00\x01')):
            raise ValueError('Encoder did not emit an immediate Annex B access unit')
        if len(data) >= 2 * 1024 * 1024: raise ValueError('Encoded frame exceeds packet limit')
        self.index += 1
        return data

    def encode(self, image):
        image = image.copy()
        image.thumbnail((1600, 1000))
        # H.264 4:2:0 requires even dimensions; resize rather than shifting the input rectangle.
        width, height = max(2, image.width // 2 * 2), max(2, image.height // 2 * 2)
        if self.prefer_h264: image = image.resize((width, height))
        if self.context and self.size != image.size:
            self.context = self._open(self.backend, image.size)
            self.size, self.index = image.size, 0
        if self.prefer_h264 and not self.probed:
            self.probed = True
            for name in self.candidates:
                try:
                    context = self._open(name, image.size)
                    data = self._encode(context, image)
                    self.context, self.size = context, image.size
                    self.codec, self.backend = 'h264', name
                    return data, *image.size, self.codec, self.backend
                except Exception:
                    self.index = 0
        if self.context:
            data = self._encode(self.context, image)
        else:
            buffer = io.BytesIO()
            image.convert('RGB').save(buffer, 'JPEG', quality=72)
            data = buffer.getvalue()
        return data, *image.size, self.codec, self.backend
