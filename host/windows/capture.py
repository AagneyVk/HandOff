"""Explicit app-window or monitor capture using bounded Win32 GDI buffers."""
import ctypes
from ctypes import wintypes as w
from PIL import Image
from .window_catalog import resolve_display, resolve_hwnd


def api():
    u = ctypes.WinDLL('user32', use_last_error=True)
    g = ctypes.WinDLL('gdi32', use_last_error=True)
    signatures = [
        (u, 'IsWindow', [w.HWND], w.BOOL), (u, 'IsIconic', [w.HWND], w.BOOL),
        (u, 'GetClientRect', [w.HWND, ctypes.POINTER(w.RECT)], w.BOOL),
        (u, 'GetWindowThreadProcessId', [w.HWND, ctypes.POINTER(w.DWORD)], w.DWORD),
        (u, 'GetDC', [w.HWND], w.HDC), (u, 'ReleaseDC', [w.HWND, w.HDC], ctypes.c_int),
        (u, 'PrintWindow', [w.HWND, w.HDC, w.UINT], w.BOOL),
        (g, 'CreateCompatibleDC', [w.HDC], w.HDC),
        (g, 'CreateCompatibleBitmap', [w.HDC, ctypes.c_int, ctypes.c_int], w.HBITMAP),
        (g, 'BitBlt', [w.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                       w.HDC, ctypes.c_int, ctypes.c_int, w.DWORD], w.BOOL),
        (g, 'SelectObject', [w.HDC, w.HANDLE], w.HANDLE),
        (g, 'DeleteObject', [w.HANDLE], w.BOOL), (g, 'DeleteDC', [w.HDC], w.BOOL),
        (g, 'GetDIBits', [w.HDC, w.HBITMAP, w.UINT, w.UINT, ctypes.c_void_p, ctypes.c_void_p, w.UINT], ctypes.c_int),
    ]
    for lib, name, args, result in signatures:
        fn = getattr(lib, name); fn.argtypes = args; fn.restype = result
    return u, g


class Header(ctypes.Structure):
    _fields_ = [('size', w.DWORD), ('width', w.LONG), ('height', w.LONG), ('planes', w.WORD),
                ('bits', w.WORD), ('compression', w.DWORD), ('image_size', w.DWORD),
                ('xppm', w.LONG), ('yppm', w.LONG), ('used', w.DWORD), ('important', w.DWORD)]


def identity(window_id):
    if window_id.startswith('display:'):
        return ('display', *resolve_display(window_id))
    u, _ = api()
    hwnd = resolve_hwnd(window_id)
    pid = w.DWORD()
    if not u.IsWindow(hwnd) or not u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)):
        raise ValueError('The selected app was closed.')
    return pid.value


def grab(window_id, expected_pid):
    u, g = api()
    if window_id.startswith('display:'):
        left, top, width, height = resolve_display(window_id)
        if identity(window_id) != expected_pid:
            raise ValueError('The selected display changed. Share it again.')
        image = _capture_bitmap(u, g, 0, left, top, width, height, use_print_window=False)
        if identity(window_id) != expected_pid: raise ValueError('The selected display changed.')
        return image
    hwnd = resolve_hwnd(window_id)
    if identity(window_id) != expected_pid:
        raise ValueError('The selected app changed. Share it again on your computer.')
    if u.IsIconic(hwnd):
        raise ValueError('Restore the selected app on your computer to continue.')
    rect = w.RECT()
    if not u.GetClientRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError(ctypes.get_last_error())
    width, height = rect.right, rect.bottom
    if not (0 < width <= 8192 and 0 < height <= 8192 and width * height <= 16777216):
        raise ValueError('The app window is too large or unavailable. Resize it and try again.')
    image = _capture_bitmap(u, g, hwnd, 0, 0, width, height, use_print_window=True)
    if identity(window_id) != expected_pid: raise ValueError('The selected app changed.')
    return image


def _capture_bitmap(u, g, source_handle, left, top, width, height, use_print_window):
    screen = u.GetDC(source_handle)
    if not screen:
        raise ctypes.WinError(ctypes.get_last_error())
    dc = bitmap = old = None
    try:
        dc = g.CreateCompatibleDC(screen)
        bitmap = g.CreateCompatibleBitmap(screen, width, height)
        if not dc or not bitmap:
            raise ctypes.WinError(ctypes.get_last_error())
        old = g.SelectObject(dc, bitmap)
        if not old or old == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        if use_print_window:
            # PW_CLIENTONLY | PW_RENDERFULLCONTENT. This call is isolated in a killable process.
            if not u.PrintWindow(source_handle, dc, 3):
                raise ValueError('This app does not support window capture.')
        elif not g.BitBlt(dc, 0, 0, width, height, screen, left, top, 0x00CC0020):
            raise ValueError('This display could not be captured.')
        g.SelectObject(dc, old); old = None
        header = Header(ctypes.sizeof(Header), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
        pixels = ctypes.create_string_buffer(width * height * 4)
        if g.GetDIBits(dc, bitmap, 0, height, pixels, ctypes.byref(header), 0) != height:
            raise ctypes.WinError(ctypes.get_last_error())
        return Image.frombytes('RGB', (width, height), pixels.raw, 'raw', 'BGRX')
    finally:
        if old: g.SelectObject(dc, old)
        if bitmap: g.DeleteObject(bitmap)
        if dc: g.DeleteDC(dc)
        u.ReleaseDC(source_handle, screen)
