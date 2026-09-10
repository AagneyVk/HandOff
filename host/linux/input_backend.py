from host.shared.protocol import normalized
from .capture import connection, window


def _input(window_id, x, y, button, count, expected_size):
    from Xlib import X
    from Xlib.ext import xtest
    d = connection()
    try:
        d.grab_server()
        root = d.screen().root
        win = window(d, window_id)
        active = root.get_full_property(d.intern_atom('_NET_ACTIVE_WINDOW'), X.AnyPropertyType)
        if active is None or not len(active.value) or int(active.value[0]) != win.id:
            raise ValueError('Bring the shared app to the foreground on your computer to control it.')
        geometry = win.get_geometry()
        if expected_size != (geometry.width, geometry.height):
            raise ValueError('Window resized. Wait for the next frame.')
        px = round(normalized(x, 'x') * (geometry.width - 1))
        py = round(normalized(y, 'y') * (geometry.height - 1))
        point = root.translate_coords(win, px, py)
        xtest.fake_input(d, X.MotionNotify, x=point.x, y=point.y)
        d.sync()
        hit = root
        seen = False
        for _ in range(32):
            if hit.id == win.id: seen = True
            child = hit.query_pointer().child
            if not child: break
            hit = child
        if not seen:
            raise ValueError('Another window covers this point.')
        for _ in range(count):
            xtest.fake_input(d, X.ButtonPress, button)
            xtest.fake_input(d, X.ButtonRelease, button)
        d.sync()
    finally:
        d.ungrab_server()
        d.flush()
        d.close()


def tap(window_id, x, y, expected_size):
    _input(window_id, x, y, 1, 1, expected_size)


def scroll(window_id, x, y, dy, expected_size):
    count = min(10, round(abs(dy)))
    if count: _input(window_id, x, y, 4 if dy > 0 else 5, count, expected_size)
