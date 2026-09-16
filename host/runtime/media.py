"""One frame in flight; capture runs in a process with a hard deadline."""
import asyncio
import io
import multiprocessing
import sys


def _worker(pipe, window, pid, prefer_h264, profile):
    try:
        if sys.platform == 'win32':
            import ctypes
            try: ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
            except (AttributeError, OSError): pass
            from host.windows.capture import grab
        else:
            from host.linux.capture import grab
        from .encoder import VideoEncoder
        encoder = VideoEncoder(prefer_h264, profile=profile)
        while pipe.recv() == 'frame':
            try:
                image = grab(window, pid)
                source = image.size
                data, width, height, codec, backend = encoder.encode(image)
                if len(data) >= 2 * 1024 * 1024:
                    raise ValueError('Frame is too large to send.')
                pipe.send((True, data, width, height, *source, codec, backend))
            except Exception as exc:
                pipe.send((False, str(exc)))
                break
    except (EOFError, BrokenPipeError):
        pass
    finally:
        pipe.close()


class Capture:
    def __init__(self, window, pid, prefer_h264=False, profile='balanced'):
        context = multiprocessing.get_context('spawn')
        self.pipe, child = context.Pipe()
        self.process = context.Process(target=_worker, args=(child, window, pid, prefer_h264, profile), daemon=True)
        self.process.start()
        child.close()

    async def frame(self):
        self.pipe.send('frame')
        # Poll without parking an executor thread on a pipe that could be closed.
        deadline = asyncio.get_running_loop().time() + 4
        while not self.pipe.poll():
            if not self.process.is_alive():
                raise ValueError('Capture process stopped. Share the app again.')
            if asyncio.get_running_loop().time() > deadline:
                raise ValueError('The app did not respond to capture. Try another app.')
            await asyncio.sleep(.01)
        result = self.pipe.recv()
        if not result[0]:
            raise ValueError(result[1])
        return result[1:]

    def close(self):
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=.5)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(timeout=.5)
        self.pipe.close()
