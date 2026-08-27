import unittest
from unittest.mock import patch

from host.windows import v1_host
from host.windows.window_catalog import WindowInfo


class WindowsV1HostTests(unittest.TestCase):
    def test_snapshot_serializes_catalog(self):
        fake = WindowInfo("win32:7", "Browser", "browser.exe", 1280, 720)
        with patch("host.windows.v1_host.list_windows", return_value=[fake]):
            self.assertEqual(v1_host.snapshot(), [{
                "id": "win32:7", "title": "Browser", "app": "browser.exe",
                "width": 1280, "height": 720,
            }])

    def test_host_name_is_nonempty(self):
        self.assertTrue(v1_host.host_name())


if __name__ == "__main__":
    unittest.main()
