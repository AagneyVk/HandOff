"""Real desktop pixels, not a mocked capture API. Enabled by CI desktop jobs."""
import os
import sys
import unittest


@unittest.skipUnless(sys.platform == 'win32' and os.environ.get('HANDOFF_NATIVE_TESTS') == '1', 'Windows desktop test')
class WindowsCaptureTests(unittest.TestCase):
    def test_captures_client_pixels_and_rejects_closed_window(self):
        import ctypes
        import tkinter as tk
        from host.windows.capture import grab, identity
        from host.windows.window_catalog import list_windows
        from host.windows.input_backend import tap
        root = tk.Tk()
        root.title('HandOff native capture fixture')
        root.geometry('320x240+50+50')
        root.configure(bg='#14b450')
        try:
            root.update()
            selected = next(w for w in list_windows() if w.title == root.title())
            pid = identity(selected.id)
            image = grab(selected.id, pid)
            self.assertEqual(image.size, (320, 240))
            red, green, blue = image.getpixel((160, 120))
            self.assertLess(red, 40); self.assertGreater(green, 150); self.assertLess(blue, 110)
            # The visible capture dimensions and the input client dimensions must agree.
            with self.assertRaises(ValueError): tap(selected.id, .5, .5, (1, 1))
        finally:
            root.destroy()
        with self.assertRaises(ValueError): grab(selected.id, pid)


@unittest.skipUnless(sys.platform.startswith('linux') and os.environ.get('HANDOFF_NATIVE_TESTS') == '1', 'X11 desktop test')
class X11CaptureTests(unittest.TestCase):
    def test_composite_pixels_do_not_capture_overlapping_window(self):
        from Xlib import X, Xatom, display
        from host.linux.capture import grab, list_windows, identity
        d = display.Display()
        root = d.screen().root
        win = root.create_window(10, 10, 320, 240, 0, d.screen().root_depth,
                                 X.InputOutput, X.CopyFromParent, background_pixel=0x14B450)
        win.set_wm_name('HandOff X11 capture fixture')
        win.change_property(d.intern_atom('_NET_WM_PID'), Xatom.CARDINAL, 32, [os.getpid()])
        root.change_property(d.intern_atom('_NET_CLIENT_LIST'), Xatom.WINDOW, 32, [win.id])
        win.map(); d.sync()
        overlay = root.create_window(10, 10, 320, 240, 0, d.screen().root_depth,
                                 X.InputOutput, X.CopyFromParent, background_pixel=0xFF0000)
        try:
            selected = next(w for w in list_windows() if w.id == f'x11:{win.id}')
            # Keep the window redirected so its backing pixmap survives occlusion.
            from Xlib.ext import composite
            win.composite_redirect_window(composite.RedirectAutomatic)
            d.sync()
            overlay.map(); d.sync()
            image = grab(selected.id, identity(selected.id))
            self.assertEqual(image.size, (320, 240))
            red, green, blue = image.getpixel((160, 120))
            self.assertLess(red, 40); self.assertGreater(green, 150); self.assertLess(blue, 110)
        finally:
            overlay.destroy(); win.destroy(); d.sync(); d.close()
