"""Tests for the TranscriptionController class."""

import unittest
from unittest.mock import MagicMock, Mock, patch, call, PropertyMock
import logging
import os
import sys
import types

# Mock PyQt6 modules before importing the controller
# Create a proper mock QObject class that can be inherited
class MockQObject:
    def __init__(self, parent=None):
        pass

mock_pyqt = MagicMock()
mock_qtcore = MagicMock()
mock_qtcore.QObject = MockQObject
mock_qtcore.pyqtSignal = MagicMock
mock_qtcore.QThread = MagicMock
sys.modules['PyQt6'] = mock_pyqt
sys.modules['PyQt6.QtCore'] = mock_qtcore

# Mock requests with submodules
mock_requests = MagicMock()
mock_requests.exceptions = MagicMock()
mock_requests.exceptions.RequestException = Exception
mock_requests.exceptions.Timeout = Exception
mock_requests.exceptions.ConnectionError = Exception
sys.modules['requests'] = mock_requests
sys.modules['requests.exceptions'] = mock_requests.exceptions

# Mock other dependencies that might not be installed
if 'torch' not in sys.modules:
    torch_stub = types.SimpleNamespace()
    torch_stub.backends = types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False))
    torch_stub.cuda = types.SimpleNamespace(
        is_available=lambda: False,
        empty_cache=lambda: None,
        get_device_properties=lambda *_: types.SimpleNamespace(total_memory=8 * 1024**3),
        memory_allocated=lambda *_: 0,
        device_count=lambda: 0,
        get_device_name=lambda *_: "GPU",
    )
    sys.modules['torch'] = torch_stub
sys.modules['torchaudio'] = MagicMock()
sys.modules['transformers'] = MagicMock()
sys.modules['pydub'] = MagicMock()
sys.modules['openai'] = MagicMock()
sys.modules['whisper'] = MagicMock()
sys.modules['pyannote'] = MagicMock()
sys.modules['pyannote.audio'] = MagicMock()
sys.modules['pyannote.audio.pipelines'] = MagicMock()
sys.modules['pyannote.audio.pipelines.speaker_diarization'] = MagicMock()

from app.controllers.transcription_controller import TranscriptionController
from app.models.recording import Recording
from app.models.view_mode import ViewMode
from app.constants import ERROR_INVALID_FILE, SUCCESS_TRANSCRIPTION


class TestTranscriptionController(unittest.TestCase):
    """Test cases for the TranscriptionController."""

    def setUp(self):
        """Set up test fixtures."""
        # Create mock db_manager
        self.db_manager = Mock()
        self.db_manager.update_recording = Mock()
        
        # Create mock parent for QObject
        self.parent = Mock()
        
        # Create controller normally now that QObject is properly mocked
        self.controller = TranscriptionController(self.db_manager, self.parent)
        
        # Replace signals with mocks for testing
        self.controller.transcription_process_started = Mock()
        self.controller.transcription_process_completed = Mock()
        self.controller.transcription_process_stopped = Mock()
        self.controller.status_update = Mock()
        self.controller.recording_status_updated = Mock()
        
        # Create mock recording
        self.recording = Mock(spec=Recording)
        self.recording.id = 1
        self.recording.file_path = "/path/to/test.wav"
        
        # Create default config
        self.config = {
            "transcription_method": "local",
            "transcription_quality": "openai/whisper-large-v3",
            "speaker_detection_enabled": False,
            "hardware_acceleration_enabled": True,
            "transcription_language": "english"
        }
        
        # Create mock busy guard callback
        self.busy_guard_callback = Mock()
        
        # Set up logger mock
        self.logger_patcher = patch('app.controllers.transcription_controller.logger')
        self.mock_logger = self.logger_patcher.start()

    def tearDown(self):
        """Clean up after each test."""
        self.logger_patcher.stop()

    # Constructor Tests
    def test_init_successful(self):
        """Test successful initialization with db_manager."""
        # Test that the controller was created properly in setUp
        self.assertIsNotNone(self.controller)
        self.assertEqual(self.controller.db_manager, self.db_manager)
        self.assertIsNone(self.controller.transcription_thread)

    # Start Method - Happy Path Tests
    @patch('app.controllers.transcription_controller.ThreadManager')
    @patch('app.controllers.transcription_controller.TranscriptionThread')
    @patch('app.controllers.transcription_controller.get_api_key')
    @patch('os.path.getsize')
    @patch('os.path.exists')
    def test_start_successful_local_transcription(self, mock_exists, mock_getsize, 
                                                  mock_get_api_key, mock_thread_class,
                                                  mock_thread_manager):
        """Test successful transcription start with local method."""
        # Set up mocks
        mock_exists.return_value = True
        mock_getsize.return_value = 10485760  # 10MB
        mock_get_api_key.return_value = None
        
        mock_thread_instance = Mock()
        mock_thread_class.return_value = mock_thread_instance
        
        mock_manager_instance = Mock()
        mock_thread_manager.instance.return_value = mock_manager_instance
        
        # Mock signal emits
        self.controller.status_update = Mock()
        self.controller.transcription_process_started = Mock()
        
        # Execute
        result = self.controller.start(self.recording, self.config, self.busy_guard_callback)
        
        # Verify
        self.assertTrue(result)
        self.controller.status_update.emit.assert_called_with("Starting transcription...")
        self.controller.transcription_process_started.emit.assert_called_once()
        
        # Verify thread creation with correct arguments
        mock_thread_class.assert_called_once_with(
            file_path="/path/to/test.wav",
            transcription_quality="openai/whisper-large-v3",
            speaker_detection_enabled=False,
            hf_auth_key=None,
            language="english",
            transcription_method="local",
            openai_api_key=None,
            hardware_acceleration_enabled=True
        )
        
        # Verify signal connections
        mock_thread_instance.completed.connect.assert_called_once()
        mock_thread_instance.update_progress.connect.assert_called_once()
        mock_thread_instance.error.connect.assert_called_once()
        mock_thread_instance.finished.connect.assert_called_once()
        
        # Verify thread registration and start
        mock_manager_instance.register_thread.assert_called_once_with(mock_thread_instance)
        mock_thread_instance.start.assert_called_once()

    @patch('app.controllers.transcription_controller.ThreadManager')
    @patch('app.controllers.transcription_controller.TranscriptionThread')
    @patch('app.controllers.transcription_controller.get_api_key')
    @patch('os.path.getsize')
    @patch('os.path.exists')
    def test_start_successful_api_transcription(self, mock_exists, mock_getsize,
                                                mock_get_api_key, mock_thread_class,
                                                mock_thread_manager):
        """Test successful transcription start with API method."""
        # Set up mocks
        mock_exists.return_value = True
        mock_getsize.return_value = 10485760
        mock_get_api_key.return_value = "sk-test-key"
        
        mock_thread_instance = Mock()
        mock_thread_class.return_value = mock_thread_instance
        
        mock_manager_instance = Mock()
        mock_thread_manager.instance.return_value = mock_manager_instance
        
        # Update config for API method
        self.config["transcription_method"] = "api"
        
        # Execute
        result = self.controller.start(self.recording, self.config, self.busy_guard_callback)
        
        # Verify
        self.assertTrue(result)
        
        # Verify API key was requested
        mock_get_api_key.assert_called_with("OPENAI_API_KEY")
        
        # Verify thread created with OpenAI API key
        mock_thread_class.assert_called_once()
        call_kwargs = mock_thread_class.call_args.kwargs
        self.assertEqual(call_kwargs["openai_api_key"], "sk-test-key")
        self.assertEqual(call_kwargs["transcription_method"], "api")

    @patch('app.controllers.transcription_controller.ThreadManager')
    @patch('app.controllers.transcription_controller.TranscriptionThread')
    @patch('app.controllers.transcription_controller.get_api_key')
    @patch('os.path.getsize')
    @patch('os.path.exists')
    def test_start_with_speaker_detection(self, mock_exists, mock_getsize,
                                          mock_get_api_key, mock_thread_class,
                                          mock_thread_manager):
        """Test transcription with speaker detection requiring HF key."""
        # Set up mocks
        mock_exists.return_value = True
        mock_getsize.return_value = 10485760
        mock_get_api_key.return_value = "hf_test_key"
        
        mock_thread_instance = Mock()
        mock_thread_class.return_value = mock_thread_instance
        
        mock_manager_instance = Mock()
        mock_thread_manager.instance.return_value = mock_manager_instance
        
        # Enable speaker detection
        self.config["speaker_detection_enabled"] = True
        
        # Execute
        result = self.controller.start(self.recording, self.config, self.busy_guard_callback)
        
        # Verify
        self.assertTrue(result)
        
        # Verify HF key was requested
        mock_get_api_key.assert_called_with("HF_API_KEY")
        
        # Verify thread created with HF auth key and speaker detection
        call_kwargs = mock_thread_class.call_args.kwargs
        self.assertEqual(call_kwargs["hf_auth_key"], "hf_test_key")
        self.assertTrue(call_kwargs["speaker_detection_enabled"])

    # Start Method - Error Cases
    def test_start_fails_with_null_recording(self):
        """Test start fails with null recording."""
        result = self.controller.start(None, self.config, self.busy_guard_callback)
        
        self.assertFalse(result)
        # Verify no thread was created
        self.assertIsNone(self.controller.transcription_thread)

    @patch('os.path.exists')
    def test_start_fails_with_missing_file(self, mock_exists):
        """Test start fails with missing file."""
        mock_exists.return_value = False
        
        result = self.controller.start(self.recording, self.config, self.busy_guard_callback)
        
        self.assertFalse(result)
        self.mock_logger.error.assert_called_once()
        error_msg = self.mock_logger.error.call_args[0][0]
        self.assertIn("File not found", error_msg)
        self.assertIsNone(self.controller.transcription_thread)

    @patch('os.path.getsize')
    @patch('os.path.exists')
    def test_start_fails_with_oversized_file(self, mock_exists, mock_getsize):
        """Test start fails with oversized file."""
        mock_exists.return_value = True
        mock_getsize.return_value = 314572801  # 300MB + 1 byte
        
        result = self.controller.start(self.recording, self.config, self.busy_guard_callback)
        
        self.assertFalse(result)
        self.mock_logger.error.assert_called_once()
        error_msg = self.mock_logger.error.call_args[0][0]
        self.assertIn("File too large", error_msg)
        self.assertIsNone(self.controller.transcription_thread)

    @patch('app.controllers.transcription_controller.get_api_key')
    @patch('os.path.getsize')
    @patch('os.path.exists')
    def test_start_fails_missing_openai_key_for_api(self, mock_exists, mock_getsize,
                                                     mock_get_api_key):
        """Test start fails with missing OpenAI API key for API method."""
        mock_exists.return_value = True
        mock_getsize.return_value = 10485760
        mock_get_api_key.return_value = None
        
        self.config["transcription_method"] = "api"
        
        result = self.controller.start(self.recording, self.config, self.busy_guard_callback)
        
        self.assertFalse(result)
        self.mock_logger.error.assert_called_once()
        error_msg = self.mock_logger.error.call_args[0][0]
        self.assertIn("OpenAI API key missing", error_msg)
        self.assertIsNone(self.controller.transcription_thread)

    @patch('app.controllers.transcription_controller.get_api_key')
    @patch('os.path.getsize')
    @patch('os.path.exists')
    def test_start_fails_missing_hf_key_for_speaker_detection(self, mock_exists, 
                                                               mock_getsize,
                                                               mock_get_api_key):
        """Test start fails with missing HF key for speaker detection."""
        mock_exists.return_value = True
        mock_getsize.return_value = 10485760
        mock_get_api_key.return_value = None
        
        self.config["speaker_detection_enabled"] = True
        
        result = self.controller.start(self.recording, self.config, self.busy_guard_callback)
        
        self.assertFalse(result)
        self.mock_logger.error.assert_called_once()
        error_msg = self.mock_logger.error.call_args[0][0]
        self.assertIn("Hugging Face API key missing", error_msg)
        self.assertIsNone(self.controller.transcription_thread)

    # Validate Inputs Method Tests
    @patch('os.path.getsize')
    @patch('os.path.exists')
    def test_validate_inputs_passes_with_valid_recording(self, mock_exists, mock_getsize):
        """Test validation passes with valid recording."""
        mock_exists.return_value = True
        mock_getsize.return_value = 52428800  # 50MB
        
        result = self.controller._validate_inputs(self.recording)
        
        self.assertTrue(result)
        self.mock_logger.error.assert_not_called()

    def test_validate_inputs_fails_with_none_recording(self):
        """Test validation fails with None recording."""
        result = self.controller._validate_inputs(None)
        
        self.assertFalse(result)
        # No file system checks should be performed
        self.mock_logger.error.assert_not_called()

    def test_validate_inputs_fails_with_empty_file_path(self):
        """Test validation fails with empty file path."""
        self.recording.file_path = ""
        
        result = self.controller._validate_inputs(self.recording)
        
        self.assertFalse(result)
        self.mock_logger.error.assert_called_once()
        error_msg = self.mock_logger.error.call_args[0][0]
        self.assertIn("File not found", error_msg)

    @patch('os.path.getsize')
    @patch('os.path.exists')
    def test_validate_inputs_at_size_boundary(self, mock_exists, mock_getsize):
        """Test validation at file size boundary (exactly 300MB)."""
        mock_exists.return_value = True
        mock_getsize.return_value = 314572800  # Exactly 300MB
        
        result = self.controller._validate_inputs(self.recording)
        
        # 300MB should still be valid (not > 300)
        self.assertTrue(result)
        self.mock_logger.error.assert_not_called()

    # Build Thread Args Method Tests
    @patch('app.controllers.transcription_controller.get_api_key')
    def test_build_thread_args_for_local_transcription(self, mock_get_api_key):
        """Test building args for local transcription."""
        mock_get_api_key.return_value = None
        
        result = self.controller._build_thread_args(self.recording, self.config)
        
        self.assertIsNotNone(result)
        self.assertEqual(result["file_path"], "/path/to/test.wav")
        self.assertEqual(result["transcription_method"], "local")
        self.assertIsNone(result["openai_api_key"])
        self.assertIsNone(result["hf_auth_key"])
        self.assertTrue(result["hardware_acceleration_enabled"])
        self.assertEqual(result["language"], "english")

    @patch('app.controllers.transcription_controller.get_api_key')
    def test_build_thread_args_with_all_features(self, mock_get_api_key):
        """Test building args with all features enabled."""
        # Mock different return values for each call
        mock_get_api_key.side_effect = ["sk-test-key", "hf-test-key"]
        
        self.config["transcription_method"] = "api"
        self.config["speaker_detection_enabled"] = True
        
        result = self.controller._build_thread_args(self.recording, self.config)
        
        self.assertIsNotNone(result)
        self.assertEqual(result["openai_api_key"], "sk-test-key")
        self.assertEqual(result["hf_auth_key"], "hf-test-key")
        self.assertEqual(result["transcription_method"], "api")
        self.assertTrue(result["speaker_detection_enabled"])

    @patch('app.controllers.transcription_controller.get_api_key')
    def test_build_thread_args_returns_none_when_api_key_missing(self, mock_get_api_key):
        """Test returns None when required API key missing."""
        mock_get_api_key.return_value = None
        
        self.config["transcription_method"] = "api"
        
        result = self.controller._build_thread_args(self.recording, self.config)
        
        self.assertIsNone(result)
        self.mock_logger.error.assert_called_once()
        error_msg = self.mock_logger.error.call_args[0][0]
        self.assertIn("OpenAI API key missing", error_msg)

    # Progress Handler Tests
    def test_on_transcription_progress(self):
        """Test progress message forwarding."""
        self.controller.status_update = Mock()
        message = "Processing audio file..."
        
        self.controller._on_transcription_progress(message)
        
        self.controller.status_update.emit.assert_called_once_with(message)

    # Completion Handler Tests
    def test_on_transcription_completed_with_speaker_labels(self):
        """Test handling formatted transcript with speaker labels."""
        self.controller.status_update = Mock()
        self.controller.transcription_process_completed = Mock()
        self.controller.recording_status_updated = Mock()
        
        transcript = "SPEAKER_00: Hello, this is a test."
        
        # Mock the database update to immediately call the callback
        def mock_update(rec_id, callback, **kwargs):
            callback()
        self.db_manager.update_recording.side_effect = mock_update
        
        self.controller._on_transcription_completed(self.recording, transcript)
        
        # Verify status update
        self.controller.status_update.emit.assert_any_call("Transcription complete. Saving...")
        
        # Verify database update was called with formatted transcript
        self.db_manager.update_recording.assert_called_once()
        call_args = self.db_manager.update_recording.call_args
        self.assertEqual(call_args[0][0], 1)  # recording_id
        self.assertEqual(call_args[1]["raw_transcript"], transcript)
        self.assertEqual(call_args[1]["raw_transcript_formatted"], f"<pre>{transcript}</pre>")
        
        # Verify signals emitted
        self.controller.status_update.emit.assert_any_call(SUCCESS_TRANSCRIPTION)
        self.controller.transcription_process_completed.emit.assert_called_once_with(transcript)
        self.controller.recording_status_updated.emit.assert_called_once()

    def test_on_transcription_completed_without_speaker_labels(self):
        """Test handling plain transcript without speaker labels."""
        self.controller.status_update = Mock()
        self.controller.transcription_process_completed = Mock()
        self.controller.recording_status_updated = Mock()
        
        transcript = "This is a plain transcript without speaker labels."
        
        # Mock the database update to immediately call the callback
        def mock_update(rec_id, callback, **kwargs):
            callback()
        self.db_manager.update_recording.side_effect = mock_update
        
        self.controller._on_transcription_completed(self.recording, transcript)
        
        # Verify database update was called without formatted field
        self.db_manager.update_recording.assert_called_once()
        call_args = self.db_manager.update_recording.call_args
        self.assertEqual(call_args[1]["raw_transcript"], transcript)
        self.assertIsNone(call_args[1]["raw_transcript_formatted"])
        
        # Verify signals emitted
        self.controller.transcription_process_completed.emit.assert_called_once_with(transcript)

    def test_on_transcription_completed_with_null_recording(self):
        """Test completion with null recording."""
        self.controller.status_update = Mock()
        self.controller.transcription_process_completed = Mock()
        self.controller.recording_status_updated = Mock()
        
        self.controller._on_transcription_completed(None, "Some transcript")
        
        # Verify no database updates or signals
        self.db_manager.update_recording.assert_not_called()
        self.controller.status_update.emit.assert_not_called()
        self.controller.transcription_process_completed.emit.assert_not_called()
        self.controller.recording_status_updated.emit.assert_not_called()

    def test_on_transcription_completed_db_callback_execution(self):
        """Test DB update callback execution."""
        self.controller.status_update = Mock()
        self.controller.transcription_process_completed = Mock()
        self.controller.recording_status_updated = Mock()
        
        transcript = "Test transcript"
        
        # Capture the callback passed to update_recording
        callback_ref = []
        def capture_callback(rec_id, callback, **kwargs):
            callback_ref.append(callback)
        self.db_manager.update_recording.side_effect = capture_callback
        
        self.controller._on_transcription_completed(self.recording, transcript)
        
        # Execute the captured callback
        callback_ref[0]()
        
        # Verify signals emitted after callback
        self.controller.status_update.emit.assert_any_call(SUCCESS_TRANSCRIPTION)
        self.controller.transcription_process_completed.emit.assert_called_once_with(transcript)
        self.controller.recording_status_updated.emit.assert_called_once_with(
            1,
            {
                "has_transcript": True,
                "raw_transcript": transcript,
                "raw_transcript_formatted": None
            }
        )

    # Error Handler Tests
    def test_on_transcription_error(self):
        """Test error message handling."""
        self.controller.status_update = Mock()
        error_msg = "Failed to load model"
        
        self.controller._on_transcription_error(error_msg)
        
        self.controller.status_update.emit.assert_called_once_with(
            f"Transcription failed: {error_msg}"
        )

    # Finished Handler Tests
    def test_on_transcription_finished(self):
        """Test cleanup when transcription finishes."""
        self.controller.status_update = Mock()
        self.controller.transcription_thread = Mock()
        
        self.controller._on_transcription_finished()
        
        self.assertIsNone(self.controller.transcription_thread)
        self.mock_logger.info.assert_called_once_with("Transcription thread finished.")
        self.controller.status_update.emit.assert_called_once_with("Ready")

    # Cancel Method Tests
    def test_cancel_running_transcription(self):
        """Test canceling running transcription."""
        self.controller.status_update = Mock()
        mock_thread = Mock()
        mock_thread.isRunning.return_value = True
        self.controller.transcription_thread = mock_thread
        
        self.controller.cancel()
        
        mock_thread.cancel.assert_called_once()
        self.mock_logger.info.assert_called_once_with("Canceling transcription...")
        self.controller.status_update.emit.assert_called_once_with("Canceling transcription...")

    def test_cancel_with_no_thread(self):
        """Test cancel with no running thread."""
        self.controller.status_update = Mock()
        self.controller.transcription_thread = None
        
        self.controller.cancel()
        
        # No errors, no signals
        self.controller.status_update.emit.assert_not_called()
        self.mock_logger.info.assert_not_called()

    def test_cancel_with_stopped_thread(self):
        """Test cancel with stopped thread."""
        self.controller.status_update = Mock()
        mock_thread = Mock()
        mock_thread.isRunning.return_value = False
        self.controller.transcription_thread = mock_thread
        
        self.controller.cancel()
        
        mock_thread.cancel.assert_not_called()
        self.controller.status_update.emit.assert_not_called()

    # Edge Cases and Integration Tests
    @patch('app.controllers.transcription_controller.ThreadManager')
    @patch('app.controllers.transcription_controller.TranscriptionThread')
    @patch('os.path.getsize')
    @patch('os.path.exists')
    def test_start_with_custom_language(self, mock_exists, mock_getsize,
                                        mock_thread_class, mock_thread_manager):
        """Test with custom language setting."""
        mock_exists.return_value = True
        mock_getsize.return_value = 10485760
        
        mock_thread_instance = Mock()
        mock_thread_class.return_value = mock_thread_instance
        
        mock_manager_instance = Mock()
        mock_thread_manager.instance.return_value = mock_manager_instance
        
        # Set Spanish language
        self.config["transcription_language"] = "spanish"
        
        result = self.controller.start(self.recording, self.config, self.busy_guard_callback)
        
        self.assertTrue(result)
        
        # Verify language parameter
        call_kwargs = mock_thread_class.call_args.kwargs
        self.assertEqual(call_kwargs["language"], "spanish")

    @patch('app.controllers.transcription_controller.ThreadManager')
    @patch('app.controllers.transcription_controller.TranscriptionThread')
    @patch('os.path.getsize')
    @patch('os.path.exists')
    def test_start_with_hardware_acceleration_disabled(self, mock_exists, mock_getsize,
                                                       mock_thread_class, mock_thread_manager):
        """Test with hardware acceleration disabled."""
        mock_exists.return_value = True
        mock_getsize.return_value = 10485760
        
        mock_thread_instance = Mock()
        mock_thread_class.return_value = mock_thread_instance
        
        mock_manager_instance = Mock()
        mock_thread_manager.instance.return_value = mock_manager_instance
        
        # Disable hardware acceleration
        self.config["hardware_acceleration_enabled"] = False
        
        result = self.controller.start(self.recording, self.config, self.busy_guard_callback)
        
        self.assertTrue(result)
        
        # Verify hardware acceleration setting
        call_kwargs = mock_thread_class.call_args.kwargs
        self.assertFalse(call_kwargs["hardware_acceleration_enabled"])

    def test_on_transcription_completed_speaker_no_colon(self):
        """Test transcript edge case with SPEAKER_ but no colon."""
        self.controller.status_update = Mock()
        self.controller.transcription_process_completed = Mock()
        self.controller.recording_status_updated = Mock()
        
        # SPEAKER_ prefix but no colon in first 20 chars
        transcript = "SPEAKER_00 said something without proper formatting"
        
        # Mock the database update to immediately call the callback
        def mock_update(rec_id, callback, **kwargs):
            callback()
        self.db_manager.update_recording.side_effect = mock_update
        
        self.controller._on_transcription_completed(self.recording, transcript)
        
        # Should be treated as unformatted
        call_args = self.db_manager.update_recording.call_args
        self.assertEqual(call_args[1]["raw_transcript"], transcript)
        self.assertIsNone(call_args[1]["raw_transcript_formatted"])

    def test_on_transcription_completed_whitespace_only(self):
        """Test with whitespace-only transcript."""
        self.controller.status_update = Mock()
        self.controller.transcription_process_completed = Mock()
        self.controller.recording_status_updated = Mock()
        
        transcript = "   \n\t   "
        
        # Mock the database update to immediately call the callback
        def mock_update(rec_id, callback, **kwargs):
            callback()
        self.db_manager.update_recording.side_effect = mock_update
        
        self.controller._on_transcription_completed(self.recording, transcript)
        
        # Should be treated as unformatted and saved as-is
        call_args = self.db_manager.update_recording.call_args
        self.assertEqual(call_args[1]["raw_transcript"], transcript)
        self.assertIsNone(call_args[1]["raw_transcript_formatted"])
        
        # Signals should still be emitted
        self.controller.transcription_process_completed.emit.assert_called_once_with(transcript)


if __name__ == "__main__":
    unittest.main()
