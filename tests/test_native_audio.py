"""Exercise real PulseAudio output loopback against a private CI null sink."""
import asyncio
import os
import sys
import unittest


@unittest.skipUnless(sys.platform.startswith('linux') and os.environ.get('HANDOFF_AUDIO_TESTS') == '1', 'PulseAudio test sink required')
class NativeAudioTests(unittest.IsolatedAsyncioTestCase):
    async def test_output_tone_reaches_bounded_capture(self):
        import numpy as np
        import soundcard as sc
        from host.runtime.audio import AudioCapture, loopback
        self.assertTrue(loopback().isloopback)
        capture = AudioCapture()
        speaker = sc.default_speaker()
        wave = np.sin(np.arange(48000 * 2) * 2 * np.pi * 440 / 48000) * .2
        samples = np.stack([wave, wave], axis=1)
        async def play():
            await asyncio.sleep(.5)
            await asyncio.to_thread(speaker.play, samples, samplerate=48000)
        task = asyncio.create_task(play())
        try:
            deadline = asyncio.get_running_loop().time() + 5
            detected = False
            while asyncio.get_running_loop().time() < deadline:
                data = await capture.chunk()
                self.assertEqual(len(data), 3840)
                if np.max(np.abs(np.frombuffer(data, dtype='<i2').astype(np.int32))) > 1000:
                    detected = True
                    break
            self.assertTrue(detected, 'Output loopback did not contain the played tone')
        finally:
            capture.close()
            await task
