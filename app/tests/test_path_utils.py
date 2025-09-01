"""Behavior-focused tests for path_utils utilities.

Covers environment detection, base path resolution, and joining behavior.
"""

import os
import sys
import unittest

from app import path_utils
from unittest import mock

from app.path_utils import resource_path, get_execution_environment, _get_base_resource_path


class TestResourcePathBehavior(unittest.TestCase):
    def test_development_env_returns_project_root_and_can_access_icons(self):
        # In dev mode, base should be the project root directory (parent of app)
        base = resource_path(env_detector=lambda: "development")
        expected_root = os.path.dirname(os.path.dirname(os.path.abspath(path_utils.__file__)))
        self.assertEqual(base, expected_root)

        # Joins relative paths and points to real resources
        icons_dir = resource_path("icons", env_detector=lambda: "development")
        self.assertTrue(os.path.isdir(icons_dir), f"Icons dir not found: {icons_dir}")

    def test_empty_relative_path_returns_base(self):
        # Empty string returns the base path (os.path.join(base, "") == base)
        base = resource_path(env_detector=lambda: "development")
        self.assertEqual(
            os.path.normpath(resource_path("", env_detector=lambda: "development")),
            os.path.normpath(base),
        )

    def test_absolute_path_is_preserved(self):
        # If an absolute path is passed, os.path.join returns the absolute path
        abs_path = "/tmp/abs/file.txt" if os.name != "nt" else "C:/abs/file.txt"
        base = resource_path(env_detector=lambda: "development")
        out = resource_path(abs_path, env_detector=lambda: "development")
        self.assertEqual(out, abs_path)
        self.assertEqual(out, os.path.join(base, abs_path))

    def test_unicode_paths(self):
        rel = "unicodé/файл.txt"
        base = resource_path(env_detector=lambda: "development")
        out = resource_path(rel, env_detector=lambda: "development")
        self.assertEqual(out, os.path.join(base, rel))

    def test_traversal_sequences_are_joined(self):
        # Function does not normalize; verify simple join happens
        rel = os.path.join("..", "..", "icons", "logo.png")
        base = resource_path(env_detector=lambda: "development")
        out = resource_path(rel, env_detector=lambda: "development")
        self.assertEqual(out, os.path.join(base, rel))


class TestExecutionEnvironment(unittest.TestCase):
    def test_get_execution_environment_pyinstaller(self):
        with mock.patch("sys._MEIPASS", "/tmp/_MEI123456", create=True):
            self.assertEqual(get_execution_environment(), "pyinstaller")

    def test_get_execution_environment_py2app(self):
        if hasattr(sys, "_MEIPASS"):
            delattr(sys, "_MEIPASS")
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "executable", "/Applications/Transcribrr.app/Contents/MacOS/transcribrr", create=True):
            self.assertEqual(get_execution_environment(), "py2app")

    def test_get_execution_environment_development(self):
        # No _MEIPASS and not a py2app executable
        if hasattr(sys, "_MEIPASS"):
            delattr(sys, "_MEIPASS")
        with mock.patch.object(sys, "frozen", False, create=True), \
             mock.patch.object(sys, "executable", "/usr/bin/python3", create=True):
            self.assertEqual(get_execution_environment(), "development")

    def test_get_execution_environment_frozen_without_macos(self):
        if hasattr(sys, "_MEIPASS"):
            delattr(sys, "_MEIPASS")
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "executable", "/usr/local/bin/python", create=True):
            self.assertEqual(get_execution_environment(), "development")


class TestBaseResourcePath(unittest.TestCase):
    def test_base_path_pyinstaller_uses_meipass(self):
        with mock.patch("sys._MEIPASS", "/tmp/_MEI987654", create=True), \
             mock.patch("app.path_utils.get_execution_environment", return_value="pyinstaller"):
            with mock.patch("app.path_utils.logger") as log:
                base = _get_base_resource_path()
                self.assertEqual(base, "/tmp/_MEI987654")
                log.debug.assert_called()

    def test_base_path_py2app_uses_resources_dir(self):
        with mock.patch("app.path_utils.get_execution_environment", return_value="py2app"), \
             mock.patch.object(sys, "executable", "/Applications/Transcribrr.app/Contents/MacOS/transcribrr", create=True), \
             mock.patch("os.path.dirname", return_value="/Applications/Transcribrr.app/Contents/MacOS"), \
             mock.patch("os.path.join", return_value="/Applications/Transcribrr.app/Contents/MacOS/../Resources"), \
             mock.patch("os.path.normpath", return_value="/Applications/Transcribrr.app/Contents/Resources"), \
             mock.patch("app.path_utils.logger") as log:
            base = _get_base_resource_path()
            self.assertEqual(base, "/Applications/Transcribrr.app/Contents/Resources")
            log.debug.assert_called()

    def test_base_path_development_uses_project_root(self):
        # Use an artificial __file__ to compute expected path
        fake_file = "/home/user/transcribrr/app/path_utils.py"
        with mock.patch("app.path_utils.get_execution_environment", return_value="development"), \
             mock.patch("app.path_utils.__file__", fake_file), \
             mock.patch("os.path.abspath", return_value=fake_file), \
             mock.patch("os.path.dirname", side_effect=["/home/user/transcribrr/app", "/home/user/transcribrr"]), \
             mock.patch("app.path_utils.logger") as log:
            base = _get_base_resource_path()
            self.assertEqual(base, "/home/user/transcribrr")
            log.debug.assert_called()

    def test_base_path_with_explicit_env_detector(self):
        fake_file = "/test/app/path_utils.py"
        with mock.patch("app.path_utils.__file__", fake_file), \
             mock.patch("os.path.abspath", return_value=fake_file), \
             mock.patch("os.path.dirname", side_effect=["/test/app", "/test"]):
            base = _get_base_resource_path(env_detector=lambda: "development")
            self.assertEqual(base, "/test")

    def test_pyinstaller_missing_meipass_raises(self):
        # If env reports pyinstaller but _MEIPASS missing, attribute access should fail
        if hasattr(sys, "_MEIPASS"):
            delattr(sys, "_MEIPASS")
        with mock.patch("app.path_utils.get_execution_environment", return_value="pyinstaller"):
            with self.assertRaises(AttributeError):
                _get_base_resource_path()

    def test_pyinstaller_none_meipass_returns_none(self):
        with mock.patch("app.path_utils.get_execution_environment", return_value="pyinstaller"), \
             mock.patch("sys._MEIPASS", None, create=True):
            base = _get_base_resource_path()
            self.assertIsNone(base)


if __name__ == "__main__":
    unittest.main()
