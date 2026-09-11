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
    kind: str = "window"

    def payload(self) -> dict:
        return asdict(self)


def _process_name(pid: int) -> str:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
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
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    windows: list[WindowInfo] = []
    monitor_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
                                           ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    def monitor_callback(monitor, _dc, rect_ptr, _lparam):
        rect = rect_ptr.contents
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if width > 0 and height > 0:
            windows.append(WindowInfo(
                id=f"display:{int(monitor)}", title=f"Entire display · {width} × {height}",
                app="Display", width=width, height=height, kind="display",
            ))
        return True

    monitor_ref = monitor_proc_type(monitor_callback)
    if not user32.EnumDisplayMonitors(0, None, monitor_ref, 0):
        raise ctypes.WinError()
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

    user32.EnumWindows.argtypes = [enum_proc_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    callback_ref = enum_proc_type(callback)
    if not user32.EnumWindows(callback_ref, 0):
        raise ctypes.WinError()
    return windows


def resolve_display(display_id: str) -> tuple[int, int, int, int]:
    if not isinstance(display_id, str) or not display_id.startswith("display:"):
        raise ValueError("not a Windows HandOff display id")
    try: wanted = int(display_id.split(":", 1)[1])
    except ValueError as exc: raise ValueError("invalid display id") from exc
    if wanted <= 0: raise ValueError("invalid display id")
    user32 = ctypes.windll.user32
    found = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
                                      ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    def callback(monitor, _dc, rect_ptr, _data):
        if int(monitor) == wanted:
            r = rect_ptr.contents; found.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True
    ref = callback_type(callback)
    user32.EnumDisplayMonitors(0, None, ref, 0)
    if not found: raise ValueError("The selected display is no longer connected.")
    return found[0]


def resolve_hwnd(window_id: str) -> int:
    if not window_id.startswith("win32:"):
        raise ValueError("not a Windows HandOff window id")
    hwnd = int(window_id.split(":", 1)[1])
    if hwnd <= 0:
        raise ValueError("invalid HWND")
    return hwnd
