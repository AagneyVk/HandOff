"""Native Windows window discovery for HandOff V1.

Uses only Win32 APIs available in the standard Python runtime through ctypes so the
catalog can be exercised in CI without introducing a GUI framework dependency.
Capture/encode will consume the stable HWND identifiers produced here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import ctypes
import os
import sys
from ctypes import wintypes


@dataclass(frozen=True)
class WindowInfo:
    id: str
    title: str
    app: str
    width: int
    height: int

    def payload(self) -> dict:
        return asdict(self)


def _process_name(pid: int) -> str:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return "Application"
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value) or "Application"
        return "Application"
    finally:
        kernel32.CloseHandle(handle)


def list_windows() -> list[WindowInfo]:
    if sys.platform != "win32":
        return []

    user32 = ctypes.windll.user32
    windows: list[WindowInfo] = []
    enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        title_buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buf, length + 1)
        title = title_buf.value.strip()
        if not title:
            return True
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if width < 64 or height < 64:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        windows.append(WindowInfo(
            id=f"win32:{int(hwnd)}", title=title, app=_process_name(pid.value),
            width=width, height=height,
        ))
        return True

    callback_ref = enum_proc_type(callback)
    if not user32.EnumWindows(callback_ref, 0):
        raise ctypes.WinError()
    return windows


def resolve_hwnd(window_id: str) -> int:
    if not window_id.startswith("win32:"):
        raise ValueError("not a Windows HandOff window id")
    hwnd = int(window_id.split(":", 1)[1])
    if hwnd <= 0:
        raise ValueError("invalid HWND")
    return hwnd
