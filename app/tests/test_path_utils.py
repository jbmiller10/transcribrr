"""Tests for path_utils.resource_path covering all environments."""

import os
import sys
import unittest
from unittest.mock import patch

from app import path_utils
from app.path_utils import resource_path


class TestResourcePath(unittest.TestCase):
    def test_dev_mode_returns_project_root(self):
        # Ensure no bundled attributes are set
        with patch.object(sys, "frozen", new=False, create=True), \
             patch.object(sys, "executable", new=sys.executable, create=True):
            base = resource_path()
            # In dev mode, base should be the project root directory (parent of app)
            expected_root = os.path.dirname(os.path.dirname(os.path.abspath(path_utils.__file__)))
            self.assertEqual(base, expected_root)

            # Joins relative paths
            rel = os.path.join("icons", "logo.png")
            full = resource_path(rel)
            self.assertEqual(full, os.path.join(base, rel))

    def test_pyinstaller_meipass_branch(self):
        fake_meipass = "/tmp/pyi12345"
        with patch.object(sys, "_MEIPASS", new=fake_meipass, create=True):
            # When running in a PyInstaller bundle, returns sys._MEIPASS
            base = resource_path()
            self.assertEqual(base, fake_meipass)
            self.assertEqual(resource_path("file.txt"), os.path.join(fake_meipass, "file.txt"))

    def test_py2app_bundle_branch(self):
        # Simulate a macOS py2app bundle: sys.frozen True and executable path .../MacOS/App
        fake_exec = "/Applications/MyApp.app/Contents/MacOS/MyApp"
        with patch.object(sys, "frozen", new=True, create=True), \
             patch.object(sys, "executable", new=fake_exec, create=True):
            base = resource_path()
            expected = os.path.normpath(os.path.join(os.path.dirname(fake_exec), os.pardir, "Resources"))
            self.assertEqual(base, expected)
            self.assertEqual(resource_path("asset.dat"), os.path.join(expected, "asset.dat"))


if __name__ == "__main__":
    unittest.main()
