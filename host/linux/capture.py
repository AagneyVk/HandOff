import os
from PIL import Image
from host.windows.window_catalog import WindowInfo


def connection():
    if os.environ.get('XDG_SESSION_TYPE') == 'wayland':
        raise ValueError('Use an X11 session. Native Wayland capture is not supported yet.')
    from Xlib.display import Display
    return Display()


def window(display, window_id):
    if not isinstance(window_id, str) or not window_id.startswith('x11:'):
        raise ValueError('Invalid X11 window')
    return display.create_resource_object('window', int(window_id[4:]))


def pid(display, win):
    from Xlib import X
    value = win.get_full_property(display.intern_atom('_NET_WM_PID'), X.AnyPropertyType)
    if value is None or not len(value.value):
        raise ValueError('This app does not publish its process identity.')
    return int(value.value[0])


def identity(window_id):
    d = connection()
    try: return pid(d, window(d, window_id))
    finally: d.close()


def list_windows():
    from Xlib import X, error
    d = connection()
    try:
        prop = d.screen().root.get_full_property(d.intern_atom('_NET_CLIENT_LIST'), X.AnyPropertyType)
        result = []
        for id_ in prop.value if prop is not None else []:
            try:
                win = d.create_resource_object('window', int(id_))
                geom = win.get_geometry()
                if win.get_attributes().map_state != X.IsViewable: continue
                pid(d, win)
                value = win.get_full_property(d.intern_atom('_NET_WM_NAME'), X.AnyPropertyType)
                title = bytes(value.value).decode('utf-8', errors='replace') if value is not None else win.get_wm_name()
                app = win.get_wm_class()
                if title and geom.width >= 64 and geom.height >= 64:
                    result.append(WindowInfo(f'x11:{int(id_)}', str(title)[:512], app[-1] if app else 'App', geom.width, geom.height))
            except (error.XError, ValueError): continue
        return result
    finally: d.close()


def grab(window_id, expected_pid):
    from Xlib import X
    from Xlib.ext import composite
    d = connection()
    pixmap = None
    try:
        if not d.has_extension('Composite'):
            raise ValueError('XComposite is required to capture only your selected app.')
        win = window(d, window_id)
        if pid(d, win) != expected_pid:
            raise ValueError('The app changed. Share it again.')
        attrs, geom = win.get_attributes(), win.get_geometry()
        if attrs.map_state != X.IsViewable:
            raise ValueError('Restore your app window to continue.')
        if not (0 < geom.width <= 8192 and 0 < geom.height <= 8192 and geom.width * geom.height <= 16777216):
            raise ValueError('Resize the app window to continue.')
        failures = []
        win.composite_redirect_window(composite.RedirectAutomatic, onerror=lambda err, _: failures.append(err))
        d.sync()
        if failures: raise ValueError('The compositor could not share this window.')
        pixmap = win.composite_name_window_pixmap(onerror=lambda err, _: failures.append(err))
        d.sync()
        if failures: raise ValueError('The app cannot be captured.')
        pixels = pixmap.get_image(geom.border_width, geom.border_width, geom.width, geom.height, X.ZPixmap, 0xFFFFFFFF)
        fmt = next(f for f in d.display.info.pixmap_formats if f.depth == geom.depth)
        visual = next(v for depth in d.screen().allowed_depths for v in depth.visuals if v.visual_id == attrs.visual)
        if (fmt.bits_per_pixel not in (24, 32) or d.display.info.image_byte_order != X.LSBFirst
                or (visual.red_mask, visual.green_mask, visual.blue_mask) != (0xFF0000, 0xFF00, 0xFF)):
            raise ValueError('This X11 pixel format is not supported.')
        stride = ((geom.width * fmt.bits_per_pixel + fmt.scanline_pad - 1) // fmt.scanline_pad) * (fmt.scanline_pad // 8)
        return Image.frombytes('RGB', (geom.width, geom.height), pixels.data, 'raw', 'BGRX' if fmt.bits_per_pixel == 32 else 'BGR', stride)
    finally:
        if pixmap: pixmap.free()
        d.close()
