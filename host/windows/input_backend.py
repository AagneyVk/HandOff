"""Windows input injection for a selected HandOff window.

V1 maps normalized client coordinates to the target window's client area and uses
SendInput for mouse events. The target HWND is validated before every operation.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from host.shared.protocol import normalized
from .window_catalog import resolve_display, resolve_hwnd

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
WHEEL_DELTA = 120


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_void_p)]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_void_p)]

class INPUTVALUE(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

class INPUT(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = [("type", wintypes.DWORD), ("value", INPUTVALUE)]


def _require_windows():
    if sys.platform != "win32":
        raise OSError("Windows input backend requires win32")


def _screen_point(window_id: str, x: float, y: float, expected_size=None) -> tuple[int, int]:
    _require_windows()
    if window_id.startswith('display:'):
        left, top, width, height = resolve_display(window_id)
        if expected_size is not None and (width, height) != expected_size:
            raise ValueError("Display geometry changed. Wait for the next frame.")
        return (left + round(normalized(x, "x") * max(0, width - 1)),
                top + round(normalized(y, "y") * max(0, height - 1)))
    hwnd = resolve_hwnd(window_id)
    user32 = ctypes.windll.user32
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    if not user32.IsWindow(hwnd):
        raise ValueError("target window no longer exists")
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError()
    if expected_size is not None and (rect.right, rect.bottom) != expected_size:
        raise ValueError("Window resized. Wait for the next frame.")
    if user32.GetForegroundWindow() != hwnd:
        raise ValueError("Bring the shared app to the foreground on your computer to control it.")
    p = wintypes.POINT(int(normalized(x, "x") * max(0, rect.right - rect.left - 1)),
                       int(normalized(y, "y") * max(0, rect.bottom - rect.top - 1)))
    if not user32.ClientToScreen(hwnd, ctypes.byref(p)):
        raise ctypes.WinError()
    hit = user32.WindowFromPoint(p)
    if user32.GetAncestor(hit, 2) != hwnd:
        raise ValueError("Another window covers this point. Move it on your computer first.")
    return p.x, p.y


def _absolute(px: int, py: int) -> tuple[int, int]:
    user32 = ctypes.windll.user32
    left = user32.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN
    top = user32.GetSystemMetrics(77)    # SM_YVIRTUALSCREEN
    width = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
    height = user32.GetSystemMetrics(79) # SM_CYVIRTUALSCREEN
    if width <= 1 or height <= 1:
        raise RuntimeError("invalid virtual desktop geometry")
    return (round((px - left) * 65535 / (width - 1)), round((py - top) * 65535 / (height - 1)))


def _send(flags: int, x: int = 0, y: int = 0, data: int = 0):
    event = INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(x, y, data & 0xFFFFFFFF, flags, 0, None))
    if ctypes.windll.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)) != 1:
        raise ctypes.WinError()


def tap(window_id: str, x: float, y: float, expected_size=None):
    px, py = _screen_point(window_id, x, y, expected_size)
    ax, ay = _absolute(px, py)
    base = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
    _send(base, ax, ay)
    _send(MOUSEEVENTF_LEFTDOWN)
    _send(MOUSEEVENTF_LEFTUP)


def scroll(window_id: str, x: float, y: float, dy: float, expected_size=None):
    px, py = _screen_point(window_id, x, y, expected_size)
    ax, ay = _absolute(px, py)
    _send(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, ax, ay)
    amount = max(-10, min(10, float(dy)))
    _send(MOUSEEVENTF_WHEEL, data=round(amount * WHEEL_DELTA))


def drag(window_id: str, x0: float, y0: float, x1: float, y1: float, expected_size=None):
    start = _screen_point(window_id, x0, y0, expected_size)
    end = _screen_point(window_id, x1, y1, expected_size)
    base = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
    ax, ay = _absolute(*start); _send(base, ax, ay); _send(MOUSEEVENTF_LEFTDOWN)
    for step in range(1, 13):
        px = round(start[0] + (end[0] - start[0]) * step / 12)
        py = round(start[1] + (end[1] - start[1]) * step / 12)
        ax, ay = _absolute(px, py); _send(base, ax, ay)
    _send(MOUSEEVENTF_LEFTUP)


def _keyboard_target(window_id: str, expected_size=None):
    _require_windows()
    if window_id.startswith('display:'):
        _, _, width, height = resolve_display(window_id)
        if expected_size is not None and (width, height) != expected_size:
            raise ValueError('Display geometry changed. Wait for the next frame.')
        return
    hwnd = resolve_hwnd(window_id)
    user32 = ctypes.windll.user32
    if not user32.IsWindow(hwnd) or user32.GetForegroundWindow() != hwnd:
        raise ValueError('Bring the shared app to the foreground before typing.')
    if expected_size is not None:
        rect = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            raise ctypes.WinError()
        if (rect.right, rect.bottom) != expected_size:
            raise ValueError('Window resized. Wait for the next frame.')


def _key_event(vk=0, scan=0, flags=0):
    event = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(vk, scan, flags, 0, None))
    if ctypes.windll.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)) != 1:
        raise ctypes.WinError()


def text(window_id: str, value: str, expected_size=None):
    _keyboard_target(window_id, expected_size)
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ValueError('Text must contain 1 to 256 characters.')
    if any(ord(ch) < 32 and ch not in '\n\t' for ch in value):
        raise ValueError('Text contains unsupported control characters.')
    for ch in value:
        if ch == '\n': key(window_id, 'enter', expected_size)
        elif ch == '\t': key(window_id, 'tab', expected_size)
        else:
            units = ch.encode('utf-16-le')
            for offset in range(0, len(units), 2):
                scan = int.from_bytes(units[offset:offset + 2], 'little')
                _key_event(scan=scan, flags=KEYEVENTF_UNICODE)
                _key_event(scan=scan, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)


def key(window_id: str, name: str, expected_size=None):
    _keyboard_target(window_id, expected_size)
    keys = {'backspace': 0x08, 'tab': 0x09, 'enter': 0x0D, 'escape': 0x1B,
            'left': 0x25, 'up': 0x26, 'right': 0x27, 'down': 0x28, 'delete': 0x2E}
    if name not in keys: raise ValueError('Unsupported key.')
    _key_event(vk=keys[name]); _key_event(vk=keys[name], flags=KEYEVENTF_KEYUP)
