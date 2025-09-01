"""Unit tests for app.ui_utils.error_handling (headless, no PyQt6 required)."""

import unittest
from unittest.mock import patch, Mock

import app.ui_utils.error_handling as eh
EH_AVAILABLE = True


@unittest.skipUnless(EH_AVAILABLE, "error_handling not importable in this environment")
class TestErrorHandling(unittest.TestCase):
    pass

    def test_handle_error_file_not_found_maps_message(self):
        msg = eh.handle_error(FileNotFoundError("/missing"), parent=None, show_dialog=False)
        self.assertIn("could not be found", msg)
        # No UI when show_dialog=False

    def test_handle_error_with_dialog_and_callback(self):
        cb = Mock()
        parent = object()
        # Inject a dummy app.ui_utils_legacy with safe_error to avoid PyQt6
        import sys, types
        dummy = types.ModuleType("app.ui_utils_legacy")
        calls = {}
        def _safe_error(p, t, m):
            calls["args"] = (p, t, m)
        dummy.safe_error = _safe_error  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"app.ui_utils_legacy": dummy}):
            msg = eh.handle_error(
                RuntimeError("boom"), parent=parent, source="transcription", title_override="Custom Title", callback=cb
            )
        self.assertIsInstance(msg, str)
        self.assertIn("Custom Title", "Custom Title")
        self.assertIn("args", calls)
        cb.assert_called_with(msg)

    def test_handle_external_library_error_openai_key(self):
        msg = eh.handle_external_library_error(Exception("API key missing"), "openai", parent=None, show_dialog=False)
        self.assertIn("API key", msg)
        # No UI when show_dialog=False

    def test_handle_external_library_error_ffmpeg_not_found(self):
        msg = eh.handle_external_library_error(Exception("ffmpeg not found on PATH"), "ffmpeg", parent=None, show_dialog=False)
        self.assertIn("FFmpeg", msg)

    def test_get_common_error_messages_has_categories(self):
        data = eh.get_common_error_messages()
        self.assertIn("network", data)
        self.assertIn("file_system", data)
        self.assertIn("api", data)


@unittest.skipUnless(EH_AVAILABLE, "error_handling not importable in this environment")
class TestErrorHandlingLogging(unittest.TestCase):
    def test_logs_warning_and_error(self):
        import logging
        records = []
        logger = logging.getLogger("transcribrr")
        class _H(logging.Handler):
            def emit(self, record):
                records.append(record)
        h = _H()
        logger.addHandler(h)
        try:
            # Warning-level for FileNotFoundError
            eh.handle_error(FileNotFoundError("missing"), parent=None, show_dialog=False)
            # Error-level with traceback for RuntimeError
            eh.handle_error(RuntimeError("boom"), parent=None, show_dialog=False)
        finally:
            logger.removeHandler(h)
        # Ensure we captured both severities
        levels = [r.levelname for r in records]
        self.assertIn("WARNING", levels)
        self.assertIn("ERROR", levels)


if __name__ == "__main__":
    unittest.main()
