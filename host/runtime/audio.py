"""Opt-in output loopback only. Never falls back to a microphone."""
import asyncio
import multiprocessing
import queue
import time

RATE = 48000
CHANNELS = 2
SAMPLES = 960
CHUNK_BYTES = SAMPLES * CHANNELS * 2


def pcm16(samples):
    import numpy as np
    if samples.shape != (SAMPLES, CHANNELS): raise ValueError('Unexpected audio layout')
    return (np.clip(np.nan_to_num(samples), -1, 1) * 32767).astype('<i2').tobytes()


def loopback():
    import soundcard as sc
    speaker = sc.default_speaker()
    if speaker is None: raise ValueError('No output audio device is available')
    microphones = sc.all_microphones(include_loopback=True)
    # Windows loopback shares the render endpoint ID. PulseAudio monitors use <sink>.monitor.
    matches = [m for m in microphones if m.isloopback and (m.id == speaker.id or m.id == speaker.id + '.monitor')]
    if not matches: raise ValueError('No loopback for the default output. Microphone capture is disabled.')
    return matches[0]


def _worker(output):
    try:
        source = loopback()
        with source.recorder(samplerate=RATE, channels=CHANNELS, blocksize=SAMPLES) as recorder:
            while True:
                item = (time.monotonic(), pcm16(recorder.record(numframes=SAMPLES)))
                try: output.put_nowait(item)
                except queue.Full:
                    # Discard old sound rather than accumulating latency.
                    try: output.get_nowait()
                    except queue.Empty: pass
                    try: output.put_nowait(item)
                    except queue.Full: pass
    except Exception as exc:
        try: output.put((0, str(exc)), timeout=.1)
        except queue.Full: pass


class AudioCapture:
    def __init__(self):
        context = multiprocessing.get_context('spawn')
        self.queue = context.Queue(maxsize=4)
        self.process = context.Process(target=_worker, args=(self.queue,), daemon=True)
        self.process.start()

    async def chunk(self):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            try:
                captured, data = self.queue.get_nowait()
                if captured == 0: raise ValueError(data)
                if time.monotonic() - captured < .15: return data
            except queue.Empty:
                if not self.process.is_alive(): raise ValueError('Audio output capture stopped')
            await asyncio.sleep(.005)
        raise ValueError('Audio device did not respond')

    def close(self):
        if self.process.is_alive(): self.process.terminate()
        self.process.join(.5)
        if self.process.is_alive(): self.process.kill(); self.process.join(.5)
        self.queue.close()
        self.queue.cancel_join_thread()
