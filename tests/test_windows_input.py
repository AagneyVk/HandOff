import sys
import unittest
from unittest import mock

from host.windows import input_backend


class WindowsInputTests(unittest.TestCase):
    def test_non_windows_rejected(self):
        if sys.platform != "win32":
            with self.assertRaises(OSError):
                input_backend._screen_point("win32:1", .5, .5)

    @unittest.skipUnless(sys.platform == "win32", "requires Windows")
    def test_invalid_hwnd_is_rejected(self):
        with self.assertRaises(ValueError):
            input_backend._screen_point("win32:999999999", .5, .5)

    def test_normalized_input_is_validated_before_use(self):
        if sys.platform == "win32":
            with mock.patch.object(input_backend.ctypes.windll.user32, "IsWindow", return_value=1), \
                 mock.patch.object(input_backend.ctypes.windll.user32, "GetClientRect", return_value=1):
                with self.assertRaises(Exception):
                    input_backend._screen_point("win32:1", 1.5, .5)


if __name__ == "__main__":
    unittest.main()
