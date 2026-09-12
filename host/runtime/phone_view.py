"""Desktop presentation and input surface for an explicitly shared Android screen."""
import queue
import threading
import tkinter as tk
from tkinter import ttk

from PIL import ImageTk


class OutputAudio:
    def __init__(self):
        self.queue = queue.Queue(4)
        self.closed = False
        self.error = None
        self.thread = threading.Thread(target=self._run, name='handoff-phone-audio', daemon=True)
        self.thread.start()

    def offer(self, data):
        if self.closed or len(data) != 3840: return
        try: self.queue.put_nowait(data)
        except queue.Full:
            try: self.queue.get_nowait()
            except queue.Empty: pass
            try: self.queue.put_nowait(data)
            except queue.Full: pass

    def _run(self):
        try:
            import numpy as np
            import soundcard as sc
            speaker = sc.default_speaker()
            if speaker is None: raise ValueError('No default computer speaker')
            with speaker.player(samplerate=48000, channels=2, blocksize=960) as player:
                while not self.closed:
                    try: data = self.queue.get(timeout=.2)
                    except queue.Empty: continue
                    player.play(np.frombuffer(data, dtype='<i2').reshape(-1, 2).astype('float32') / 32768.0)
        except Exception as exc: self.error = str(exc)
        finally: self.closed = True

    def close(self):
        self.closed = True
        self.thread.join(timeout=.5)


class PhonePresenter:
    """Decodes on the network thread; performs every Tk mutation on the Tk thread."""
    def __init__(self, root, send_control):
        self.root, self.send_control = root, send_control
        self.owner = self.window = self.canvas = None
        self.decoder = self.audio = self.photo = self.image = None
        self.width = self.height = 0
        self.drag_start = None
        self.lock = threading.Lock()
        self.ui_queue = queue.Queue()
        self.dirty = threading.Event()
        self.control_label = None
        self.root.after(16, self._poll)

    def start(self, owner, width, height, audio, controls):
        import av
        with self.lock:
            if self.owner is not None: raise ValueError('A phone screen is already open.')
            self.owner, self.width, self.height = owner, width, height
            self.decoder = av.CodecContext.create('h264', 'r')
            self.decoder.thread_count = 1
            self.audio = OutputAudio() if audio else None
            self.controls = controls
        self.ui_queue.put('open')

    def _open(self):
        if self.owner is None: return
        window = tk.Toplevel(self.root); self.window = window
        window.title('HandOff · Phone')
        window.geometry('520x820')
        window.minsize(320, 480)
        frame = ttk.Frame(window); frame.pack(fill='both', expand=True)
        bar = ttk.Frame(frame, padding=8); bar.pack(fill='x')
        ttk.Label(bar, text='PHONE ON THIS COMPUTER', foreground='#006b58', font=('Segoe UI', 10, 'bold')).pack(side='left')
        self.control_label = ttk.Label(bar)
        self.control_label.pack(side='left', padx=12)
        self._control_status()
        ttk.Button(bar, text='Return to phone', command=lambda: self.send_control(self.owner, 'phone.stop')).pack(side='right')
        self.canvas = tk.Canvas(frame, bg='black', highlightthickness=0, takefocus=True)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda _event: self._render())
        self.canvas.bind('<ButtonPress-1>', self._press)
        self.canvas.bind('<ButtonRelease-1>', self._release)
        self.canvas.bind('<MouseWheel>', self._wheel)
        self.canvas.bind('<Button-4>', lambda event: self._wheel(event, 1))
        self.canvas.bind('<Button-5>', lambda event: self._wheel(event, -1))
        self.canvas.bind('<KeyPress>', self._key)
        window.protocol('WM_DELETE_WINDOW', lambda: self.send_control(self.owner, 'phone.stop'))
        self.canvas.focus_set()
        self._render()

    def feed_video(self, data):
        import av
        with self.lock:
            if not self.decoder: return False
            frames = self.decoder.decode(av.Packet(data))
            if not frames: return False
            self.image = frames[-1].to_image().convert('RGB')
        self.dirty.set()
        return True

    def set_controls(self, owner, enabled):
        if owner is not self.owner: return
        self.controls = enabled
        self.ui_queue.put('controls')

    def _control_status(self):
        if self.control_label:
            self.control_label.configure(text='Control on' if self.controls else 'View only · enable phone control in HandOff')

    def feed_audio(self, data):
        with self.lock:
            if self.audio: self.audio.offer(data)

    def _bounds(self):
        if not self.canvas: return None
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw <= 1 or ch <= 1 or self.width <= 0 or self.height <= 0: return None
        scale = min(cw / self.width, ch / self.height)
        w, h = self.width * scale, self.height * scale
        return (cw - w) / 2, (ch - h) / 2, w, h

    def _point(self, event):
        bounds = self._bounds()
        if not bounds: return None
        left, top, width, height = bounds
        x, y = (event.x - left) / width, (event.y - top) / height
        return (x, y) if 0 <= x <= 1 and 0 <= y <= 1 else None

    def _press(self, event):
        self.canvas.focus_set(); self.drag_start = self._point(event)

    def _release(self, event):
        end, start = self._point(event), self.drag_start; self.drag_start = None
        if not start or not end or self.owner is None: return
        if abs(start[0] - end[0]) + abs(start[1] - end[1]) < .012:
            self.send_control(self.owner, 'phone.tap', x=end[0], y=end[1])
        else: self.send_control(self.owner, 'phone.drag', x0=start[0], y0=start[1], x1=end[0], y1=end[1])

    def _wheel(self, event, linux=None):
        point = self._point(event)
        if point and self.owner is not None:
            delta = linux if linux is not None else (1 if event.delta > 0 else -1)
            self.send_control(self.owner, 'phone.scroll', x=point[0], y=point[1], dy=delta)

    def _key(self, event):
        if self.owner is None: return 'break'
        names = {'Return': 'enter', 'BackSpace': 'backspace', 'Escape': 'back',
                 'Left': 'left', 'Right': 'right', 'Up': 'up', 'Down': 'down', 'Home': 'home'}
        if event.keysym in names: self.send_control(self.owner, 'phone.key', key=names[event.keysym])
        elif event.char and event.char.isprintable(): self.send_control(self.owner, 'phone.text', text=event.char)
        return 'break'

    def _render(self):
        if not self.canvas or not self.canvas.winfo_exists() or self.image is None: return
        bounds = self._bounds()
        if not bounds: return
        left, top, width, height = bounds
        display = self.image.resize((max(1, round(width)), max(1, round(height))))
        self.photo = ImageTk.PhotoImage(display)
        self.canvas.delete('all'); self.canvas.create_image(round(left), round(top), image=self.photo, anchor='nw')

    def stop(self, owner=None):
        with self.lock:
            if owner is not None and owner is not self.owner: return
            self.owner = None
            if self.audio: self.audio.close()
            self.audio = self.decoder = self.image = None
        self.ui_queue.put('close')

    def _poll(self):
        try:
            while True:
                action = self.ui_queue.get_nowait()
                if action == 'open': self._open()
                elif action == 'controls': self._control_status()
                elif action == 'close': self._close_window()
        except queue.Empty: pass
        if self.dirty.is_set():
            self.dirty.clear()
            self._render()
        try: self.root.after(16, self._poll)
        except tk.TclError: pass

    def _close_window(self):
        if self.window:
            try: self.window.destroy()
            except tk.TclError: pass
        self.window = self.canvas = self.photo = self.control_label = None
