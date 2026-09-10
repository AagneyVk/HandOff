"""Windows input injection for a selected HandOff window.

V1 maps normalized client coordinates to the target window's client area and uses
SendInput for mouse events. The target HWND is validated before every operation.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from host.shared.protocol import normalized
from .window_catalog import resolve_hwnd

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000
WHEEL_DELTA = 120


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_void_p)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("mi", MOUSEINPUT)]


def _require_windows():
    if sys.platform != "win32":
        raise OSError("Windows input backend requires win32")


def _screen_point(window_id: str, x: float, y: float, expected_size=None) -> tuple[int, int]:
    _require_windows()
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
    event = INPUT(INPUT_MOUSE, MOUSEINPUT(x, y, data & 0xFFFFFFFF, flags, 0, None))
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

