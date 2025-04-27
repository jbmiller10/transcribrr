from app.models.view_mode import ViewMode
from app.models.recording import Recording
import unittest
from unittest.mock import MagicMock, patch, ANY
import os

# Create stubs for PyQt6
import sys
import types

sys.modules.setdefault("PyQt6", types.ModuleType("PyQt6"))
qt_core = types.ModuleType("PyQt6.QtCore")

# Add stub classes


class QObject:
    def __init__(self, *args, **kwargs):
        pass


class Signal:
    def __init__(self, *args):
        pass

    def connect(self, func):
        pass

    def emit(self, *args):
        pass

    def disconnect(self):
        pass


# Assign stub classes to PyQt6 modules
qt_core.QObject = QObject
qt_core.pyqtSignal = Signal

# Assign modules to sys.modules
sys.modules["PyQt6.QtCore"] = qt_core

# Import the Recording dataclass

# Create mock for dependencies before importing the class under test
with (
    patch(
        "app.controllers.transcription_controller.TranscriptionThread"
    ) as MockTranscriptionThread,
    patch(
        "app.controllers.transcription_controller.ThreadManager"
    ) as MockThreadManager,
    patch(
        "app.controllers.transcription_controller.get_api_key",
        return_value="fake-api-key",
    ),
    patch("app.controllers.transcription_controller.os.path.exists",
          return_value=True),
    patch(
        "app.controllers.transcription_controller.os.path.getsize",
        return_value=1024 * 1024,
    ),
):  # 1MB

    # Set up mock thread manager
    mock_tm_instance = MagicMock()
    MockThreadManager.instance.return_value = mock_tm_instance

    # Now import the class under test
    from app.controllers.transcription_controller import TranscriptionController


class TestTranscriptionController(unittest.TestCase):
    """Test cases for the TranscriptionController."""

    def setUp(self):
        # Create a mock database manager
        self.db_manager = MagicMock()

        # Create the controller
        self.controller = TranscriptionController(self.db_manager)

        # Create a sample recording
        self.recording = Recording(
            id=123,
            filename="test_recording.mp3",
            file_path="/path/to/test_recording.mp3",
            date_created="2023-01-01 12:00:00",
            duration=60.0,
            raw_transcript=None,
            processed_text=None,
        )

        # Sample config
        self.config = {
            "transcription_method": "local",
            "transcription_quality": "openai/whisper-large-v3",
            "speaker_detection_enabled": False,
            "hardware_acceleration_enabled": True,
            "transcription_language": "english",
            "chunk_enabled": False,
            "chunk_duration": 5,
        }

        # BusyGuard mock
        self.busy_guard_mock = MagicMock()
        self.busy_guard_callback = MagicMock(return_value=self.busy_guard_mock)

    def test_start_transcription(self):
        """Test starting a transcription."""
        # Call the method
        result = self.controller.start(
            self.recording, self.config, self.busy_guard_callback
        )

        # Verify result
        self.assertTrue(result)

        # Verify thread was created with correct arguments
        from app.controllers.transcription_controller import TranscriptionThread

        TranscriptionThread.assert_called_once()

        # Verify thread was registered and started
        thread_manager = TranscriptionThread.return_value
        self.controller.transcription_thread.start.assert_called_once()

        # Verify signals were emitted
        self.controller.status_update.emit.assert_called()
        self.controller.transcription_process_started.emit.assert_called_once()

    def test_input_validation(self):
        """Test validation of transcription inputs."""
        # Test with missing recording
        result = self.controller._validate_inputs(None)
        self.assertFalse(result)

        # Test with file path that doesn't exist (by mocking exists to return False)
        with patch(
            "app.controllers.transcription_controller.os.path.exists",
            return_value=False,
        ):
            result = self.controller._validate_inputs(self.recording)
            self.assertFalse(result)

        # Test with file that's too large (by mocking getsize to return a large value)
        with patch(
            "app.controllers.transcription_controller.os.path.getsize",
            return_value=350 * 1024 * 1024,
        ):  # 350MB
            result = self.controller._validate_inputs(self.recording)
            self.assertFalse(result)

    def test_build_thread_args(self):
        """Test building arguments for the transcription thread."""
        # Test with local transcription (default)
        args = self.controller._build_thread_args(self.recording, self.config)
        self.assertIsNotNone(args)
        self.assertEqual(args["file_path"], self.recording.file_path)
        self.assertEqual(args["transcription_method"], "local")
        self.assertFalse(args["speaker_detection_enabled"])

        # Test with API transcription
        config_api = self.config.copy()
        config_api["transcription_method"] = "api"

        # This should succeed since we mocked get_api_key
        args = self.controller._build_thread_args(self.recording, config_api)
        self.assertIsNotNone(args)
        self.assertEqual(args["transcription_method"], "api")
        self.assertEqual(args["openai_api_key"], "fake-api-key")

        # Test with speaker detection
        config_speaker = self.config.copy()
        config_speaker["speaker_detection_enabled"] = True

        # This should succeed since we mocked get_api_key
        args = self.controller._build_thread_args(
            self.recording, config_speaker)
        self.assertIsNotNone(args)
        self.assertTrue(args["speaker_detection_enabled"])
        self.assertEqual(args["hf_auth_key"], "fake-api-key")

    def test_on_transcription_completed(self):
        """Test handling completion of transcription."""
        # Mock transcript
        transcript = "This is a test transcript."

        # Call the method
        self.controller._on_transcription_completed(self.recording, transcript)

        # Verify database update was called
        self.db_manager.update_recording.assert_called_once_with(
            self.recording.id,
            ANY,
            raw_transcript=transcript,
            raw_transcript_formatted=None,
        )

        # Test with formatted transcript (speaker labels)
        formatted_transcript = (
            "SPEAKER_0: This is speaker 0.\nSPEAKER_1: This is speaker 1."
        )
        self.db_manager.update_recording.reset_mock()

        self.controller._on_transcription_completed(
            self.recording, formatted_transcript
        )

        # Verify database update was called with formatting
        self.db_manager.update_recording.assert_called_once_with(
            self.recording.id,
            ANY,
            raw_transcript=formatted_transcript,
            raw_transcript_formatted=f"<pre>{formatted_transcript}</pre>",
        )

    def test_cancel(self):
        """Test cancelling an ongoing transcription."""
        # Create mock thread
        self.controller.transcription_thread = MagicMock()
        self.controller.transcription_thread.isRunning.return_value = True

        # Call the method
        self.controller.cancel()

        # Verify thread was cancelled
        self.controller.transcription_thread.cancel.assert_called_once()
        self.controller.status_update.emit.assert_called_with(
            "Canceling transcription..."
        )


if __name__ == "__main__":
    unittest.main()
