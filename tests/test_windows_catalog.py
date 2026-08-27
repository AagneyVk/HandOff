import sys
import unittest

from host.windows.window_catalog import list_windows, resolve_hwnd


class WindowsCatalogTests(unittest.TestCase):
    def test_resolve_hwnd(self):
        self.assertEqual(resolve_hwnd("win32:123"), 123)
        for bad in ("fake:1", "win32:0", "win32:-1", "win32:nope"):
            with self.assertRaises(ValueError):
                resolve_hwnd(bad)

    @unittest.skipUnless(sys.platform == "win32", "requires Windows")
    def test_enumeration_returns_valid_records(self):
        # Hosted CI can have no interactive user windows, so an empty catalog is valid.
        for window in list_windows():
            self.assertTrue(window.id.startswith("win32:"))
            self.assertTrue(window.title)
            self.assertGreaterEqual(window.width, 64)
            self.assertGreaterEqual(window.height, 64)


if __name__ == "__main__":
    unittest.main()
