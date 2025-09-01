"""Test the thread launcher functionality using the real method."""

import unittest
from unittest.mock import MagicMock, patch
import sys
import types

# Provide a minimal torch stub to satisfy imports without pulling the full ML stack
sys.modules.setdefault("torch", types.ModuleType("torch"))
# Stub out optional docs-related dependency pulled by TextEditor
sys.modules.setdefault("docx", types.ModuleType("docx"))
_htmldocx = types.ModuleType("htmldocx")
class _HtmlToDocx:
    def add_html_to_document(self, *a, **k):
        pass
HtmlToDocx = _HtmlToDocx
_htmldocx.HtmlToDocx = _HtmlToDocx
sys.modules.setdefault("htmldocx", _htmldocx)

# Minimal moviepy stubs used by file_utils import chain
_moviepy = types.ModuleType("moviepy")
_moviepy_editor = types.ModuleType("moviepy.editor")
class _Clip:
    def __init__(self, *a, **k):
        pass
    def close(self):
        pass
VideoFileClip = _Clip
AudioFileClip = _Clip
_moviepy_editor.VideoFileClip = _Clip
_moviepy_editor.AudioFileClip = _Clip
sys.modules.setdefault("moviepy", _moviepy)
sys.modules.setdefault("moviepy.editor", _moviepy_editor)

# Minimal pydub stub
_pydub = types.ModuleType("pydub")
class _AudioSegment:
    @classmethod
    def from_file(cls, *a, **k):
        return cls()
AudioSegment = _AudioSegment
_pydub.AudioSegment = _AudioSegment
sys.modules.setdefault("pydub", _pydub)

from app.MainTranscriptionWidget import MainTranscriptionWidget as MTW


class MockThread:  # Lightweight thread-like object exposing signal attributes
    """Mock thread for testing signal connections."""

    def __init__(self):
        """Initialize signals."""
        self.completed = MagicMock()
        self.update_progress = MagicMock()
        self.error = MagicMock()
        self.finished = MagicMock()
        self.start = MagicMock()


class TestThreadLauncher(unittest.TestCase):
    """Test MainTranscriptionWidget._launch_thread behavior."""

    @patch("app.ThreadManager.ThreadManager.instance")
    def test_launch_thread_connects_signals(self, mock_thread_manager_instance):
        """Test that _launch_thread connects all signals correctly."""
        # Set up the ThreadManager mock
        thread_manager = MagicMock()
        mock_thread_manager_instance.return_value = thread_manager

        # Create a minimal instance without invoking heavy __init__
        widget = MTW.__new__(MTW)

        # Create mock handlers
        completion_handler = MagicMock()
        progress_handler = MagicMock()
        error_handler = MagicMock()
        finished_handler = MagicMock()

        # Create a mock thread
        mock_thread = MockThread()

        # Call _launch_thread
        result = MTW._launch_thread(
            widget,
            thread=mock_thread,
            completion_handler=completion_handler,
            progress_handler=progress_handler,
            error_handler=error_handler,
            finished_handler=finished_handler,
            thread_attr_name="test_thread",
        )

        # Verify signal connections
        mock_thread.completed.connect.assert_called_once_with(
            completion_handler)
        mock_thread.update_progress.connect.assert_called_once_with(
            progress_handler)
        mock_thread.error.connect.assert_called_once_with(error_handler)
        mock_thread.finished.connect.assert_called_once_with(finished_handler)

        # Verify thread registration
        thread_manager.register_thread.assert_called_once_with(mock_thread)

        # Verify thread start
        mock_thread.start.assert_called_once()

        # Verify thread attribute set
        self.assertEqual(getattr(widget, "test_thread"), mock_thread)

        # Verify method returns the thread
        self.assertEqual(result, mock_thread)

    @patch("app.ThreadManager.ThreadManager.instance")
    def test_launch_thread_without_attribute_name(self, mock_thread_manager_instance):
        """Test that _launch_thread works when no thread_attr_name is provided."""
        # Set up the ThreadManager mock
        thread_manager = MagicMock()
        mock_thread_manager_instance.return_value = thread_manager

        # Create a minimal instance without invoking heavy __init__
        widget = MTW.__new__(MTW)

        # Create mock handlers
        completion_handler = MagicMock()
        progress_handler = MagicMock()
        error_handler = MagicMock()
        finished_handler = MagicMock()

        # Create a mock thread
        mock_thread = MockThread()

        # Call _launch_thread without thread_attr_name
        result = MTW._launch_thread(
            widget,
            thread=mock_thread,
            completion_handler=completion_handler,
            progress_handler=progress_handler,
            error_handler=error_handler,
            finished_handler=finished_handler,
        )

        # Verify signal connections still made
        mock_thread.completed.connect.assert_called_once_with(
            completion_handler)
        mock_thread.update_progress.connect.assert_called_once_with(
            progress_handler)
        mock_thread.error.connect.assert_called_once_with(error_handler)
        mock_thread.finished.connect.assert_called_once_with(finished_handler)

        # Verify thread registration still done
        thread_manager.register_thread.assert_called_once_with(mock_thread)

        # Verify thread start still called
        mock_thread.start.assert_called_once()

        # Verify method returns the thread
        self.assertEqual(result, mock_thread)


if __name__ == "__main__":
    unittest.main()
