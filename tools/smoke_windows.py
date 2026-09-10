"""Launch the shipped executable and require a working native top-level UI."""
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from PIL import ImageGrab

u = ctypes.windll.user32
u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
u.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]

with tempfile.TemporaryDirectory() as folder:
    process = subprocess.Popen([sys.argv[1]], env=dict(os.environ, LOCALAPPDATA=folder))
    windows = []
    def enumerate_window(hwnd, _):
        pid = wintypes.DWORD(); u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == process.pid:
            title = ctypes.create_unicode_buffer(256); u.GetWindowTextW(hwnd, title, 256)
            if title.value == 'HandOff': windows.append(hwnd)
        return True
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None: raise RuntimeError('Packaged app exited before opening its UI')
            u.EnumWindows(callback_type(enumerate_window), 0)
            if windows: break
            time.sleep(.2)
        if not windows: raise RuntimeError('Packaged app did not show its main window')
        time.sleep(2)
        Path('artifacts').mkdir(exist_ok=True)
        ImageGrab.grab(window=int(windows[0])).save('artifacts/windows-desktop.png')
        u.PostMessageW(windows[0], 0x0010, 0, 0)
        if process.wait(timeout=10) != 0: raise RuntimeError('Packaged app did not shut down cleanly')
        print('Packaged HandOff opened and closed successfully')
    finally:
        if process.poll() is None:
            process.kill(); process.wait()
