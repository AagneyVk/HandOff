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


def _screen_point(window_id: str, x: float, y: float) -> tuple[int, int]:
    _require_windows()
    hwnd = resolve_hwnd(window_id)
    user32 = ctypes.windll.user32
    if not user32.IsWindow(hwnd):
        raise ValueError("target window no longer exists")
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError()
    p = wintypes.POINT(int(normalized(x, "x") * max(0, rect.right - rect.left - 1)),
                       int(normalized(y, "y") * max(0, rect.bottom - rect.top - 1)))
    if not user32.ClientToScreen(hwnd, ctypes.byref(p)):
        raise ctypes.WinError()
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


def tap(window_id: str, x: float, y: float):
    px, py = _screen_point(window_id, x, y)
    ax, ay = _absolute(px, py)
    base = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
    _send(base, ax, ay)
    _send(MOUSEEVENTF_LEFTDOWN)
    _send(MOUSEEVENTF_LEFTUP)


def scroll(window_id: str, x: float, y: float, dy: float):
    px, py = _screen_point(window_id, x, y)
    ax, ay = _absolute(px, py)
    _send(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, ax, ay)
    amount = max(-10, min(10, float(dy)))
    _send(MOUSEEVENTF_WHEEL, data=round(amount * WHEEL_DELTA))
