"""Unit tests for app.ui_utils.error_handling (headless)."""

import sys
import types
import unittest
from unittest.mock import patch, Mock

# Try to import the module with headless stubs; if it still fails, mark unavailable
sys.modules.setdefault("PyQt6", types.ModuleType("PyQt6"))
qtwidgets = types.ModuleType("PyQt6.QtWidgets")
class _QWidget: pass
qtwidgets.QWidget = _QWidget
sys.modules.setdefault("PyQt6.QtWidgets", qtwidgets)

try:
    import app.ui_utils.error_handling as eh
    EH_AVAILABLE = True
except Exception:
    eh = None  # type: ignore
    EH_AVAILABLE = False


@unittest.skipUnless(EH_AVAILABLE, "error_handling not importable in this environment")
class TestErrorHandling(unittest.TestCase):
    def setUp(self):
        # Patch logger to keep output quiet and assert calls
        self.logger_patcher = patch("app.ui_utils.error_handling.logger")
        self.mock_logger = self.logger_patcher.start()
        # Patch safe_error to avoid real UI
        self.safe_error_patcher = patch("app.ui_utils.error_handling.safe_error")
        self.mock_safe_error = self.safe_error_patcher.start()
        # Patch redact to a predictable function
        self.redact_patcher = patch("app.ui_utils.error_handling.redact", side_effect=lambda s: f"redacted:{s}")
        self.redact_patcher.start()

    def tearDown(self):
        self.redact_patcher.stop()
        self.safe_error_patcher.stop()
        self.logger_patcher.stop()

    def test_handle_error_file_not_found_maps_message(self):
        msg = eh.handle_error(FileNotFoundError("/missing"), parent=None, show_dialog=False)
        self.assertIn("could not be found", msg)
        self.mock_logger.warning.assert_called()
        self.mock_safe_error.assert_not_called()

    def test_handle_error_with_dialog_and_callback(self):
        cb = Mock()
        parent = object()
        msg = eh.handle_error(RuntimeError("boom"), parent=parent, source="transcription", title_override="Custom Title", callback=cb)
        self.assertIsInstance(msg, str)
        self.mock_logger.error.assert_called()
        self.mock_safe_error.assert_called()
        cb.assert_called_with(msg)

    def test_handle_external_library_error_openai_key(self):
        msg = eh.handle_external_library_error(Exception("API key missing"), "openai", parent=None, show_dialog=False)
        self.assertIn("API key", msg)
        self.mock_logger.error.assert_called()
        self.mock_safe_error.assert_not_called()

    def test_handle_external_library_error_ffmpeg_not_found(self):
        msg = eh.handle_external_library_error(Exception("ffmpeg not found on PATH"), "ffmpeg", parent=None, show_dialog=False)
        self.assertIn("FFmpeg", msg)

    def test_get_common_error_messages_has_categories(self):
        data = eh.get_common_error_messages()
        self.assertIn("network", data)
        self.assertIn("file_system", data)
        self.assertIn("api", data)


if __name__ == "__main__":
    unittest.main()
