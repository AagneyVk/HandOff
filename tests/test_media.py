import importlib.util
import io
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from host.runtime.encoder import VideoEncoder
from host.runtime.audio import pcm16, loopback, CHUNK_BYTES


class MediaTests(unittest.TestCase):
    def test_stream_profiles_bound_resolution(self):
        image = Image.new('RGB', (3000, 2000), 'green')
        self.assertEqual(VideoEncoder(profile='smooth').encode(image)[1:3], (1080, 720))
        self.assertEqual(VideoEncoder(profile='sharp').encode(image)[1:3], (1620, 1080))

    def test_unavailable_hardware_falls_back_to_real_jpeg(self):
        encoder = VideoEncoder(True, candidates=('not_a_real_encoder',))
        data, width, height, codec, backend = encoder.encode(Image.new('RGB', (101, 77), 'green'))
        self.assertEqual((codec, backend), ('jpeg', 'jpeg'))
        self.assertEqual(Image.open(io.BytesIO(data)).size, (width, height))

    @unittest.skipUnless(importlib.util.find_spec('av'), 'PyAV installed in CI')
    def test_h264_roundtrip_and_resize(self):
        import av
        encoder = VideoEncoder(True, candidates=('libx264',))
        decoder = av.CodecContext.create('h264', 'r')
        for size in [(64, 48), (64, 48), (96, 64)]:
            data, width, height, codec, backend = encoder.encode(Image.new('RGB', size, (20, 180, 80)))
            self.assertEqual((codec, backend), ('h264', 'libx264'))
            frames = decoder.decode(av.Packet(data))
            self.assertEqual(len(frames), 1)
            self.assertEqual((frames[0].width, frames[0].height), size)
            self.assertGreater(frames[0].to_image().getpixel((20, 20))[1], 160)

    @unittest.skipUnless(importlib.util.find_spec('av'), 'PyAV installed in CI')
    def test_phone_presenter_decodes_annex_b(self):
        from unittest.mock import Mock
        from host.runtime.phone_view import PhonePresenter
        encoder = VideoEncoder(True, candidates=('libx264',))
        data = encoder.encode(Image.new('RGB', (64, 48), (20, 180, 80)))[0]
        presenter = PhonePresenter(Mock(), Mock())
        owner = object(); presenter.start(owner, 64, 48, False, True)
        self.assertTrue(presenter.feed_video(data))
        self.assertEqual(presenter.image.size, (64, 48))
        for _ in range(12):
            self.assertTrue(presenter.feed_video(encoder.encode(Image.new('RGB', (64, 48), 'red'))[0]))
        self.assertEqual(presenter.ui_queue.qsize(), 1, 'Rendering must coalesce, not queue every frame')
        self.assertTrue(presenter.dirty.is_set())
        presenter.set_controls(owner, False)
        self.assertFalse(presenter.controls)
        presenter.stop(owner)

    def test_audio_clamps_nonfinite_and_has_fixed_little_endian_layout(self):
        import numpy as np
        samples = np.zeros((960, 2)); samples[0] = [2, -2]; samples[1] = [float('nan'), .5]
        data = pcm16(samples)
        self.assertEqual(len(data), CHUNK_BYTES)
        self.assertEqual(data[:4], b'\xff\x7f\x01\x80')
        self.assertEqual(data[4:6], b'\x00\x00')

    def test_audio_never_selects_microphone(self):
        speaker = SimpleNamespace(id='output')
        microphone = SimpleNamespace(id='output', isloopback=False)
        fake = SimpleNamespace(default_speaker=lambda: speaker, all_microphones=lambda **_: [microphone])
        with patch.dict(sys.modules, {'soundcard': fake}):
            with self.assertRaises(ValueError): loopback()
            monitor = SimpleNamespace(id='output.monitor', isloopback=True)
            fake.all_microphones = lambda **_: [microphone, monitor]
            self.assertIs(loopback(), monitor)
