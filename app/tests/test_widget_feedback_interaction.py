import unittest
from unittest.mock import MagicMock, patch

# Check for PyQt6 availability
try:
    from app.MainTranscriptionWidget import MainTranscriptionWidget

    HAVE_MAIN = True
except ImportError:
    HAVE_MAIN = False

try:
    from app.ControlPanelWidget import ControlPanelWidget

    HAVE_CONTROL = True
except ImportError:
    HAVE_CONTROL = False


@unittest.skipUnless(HAVE_MAIN, "PyQt6 or MainTranscriptionWidget not available")
class TestMainTranscriptionWidgetFeedback(unittest.TestCase):
    def setUp(self):
        # Create instance without running __init__
        self.widget = MainTranscriptionWidget.__new__(MainTranscriptionWidget)
        # Stub feedback_manager and config_manager
        self.widget.feedback_manager = MagicMock()
        self.widget.config_manager = MagicMock()
        # Stub status_update signal
        self.widget.status_update = MagicMock()
        self.widget.status_update.emit = MagicMock()
        # Provide necessary config
        self.widget.config_manager.get_all.return_value = {
            "transcription_method": "local",
            "transcription_quality": "hq",
            "speaker_detection_enabled": False,
            "hardware_acceleration_enabled": False,
            "transcription_language": "english",
            "chunk_enabled": False,
            "chunk_duration": 5,
        }
        # Stub file and recording data
        self.widget.current_recording_data = {
            "file_path": "dummy.wav", "id": "123"}
        # Patch filesystem and utilities
        patch_os = patch("os.path.exists", return_value=True)
        patch_valid = patch(
            "app.MainTranscriptionWidget.is_valid_media_file", return_value=True
        )
        patch_size = patch(
            "app.MainTranscriptionWidget.check_file_size", return_value=(True, 1.0)
        )
        patch_api = patch(
            "app.MainTranscriptionWidget.get_api_key", return_value="key")
        # Patch thread classes to avoid Qt dependencies
        patch_thread = patch(
            "app.MainTranscriptionWidget.TranscriptionThread", new=MagicMock
        )
        patch_tm = patch("app.MainTranscriptionWidget.ThreadManager")
        for p in (patch_os, patch_valid, patch_size, patch_api, patch_thread, patch_tm):
            p.start()
            self.addCleanup(p.stop)

    def test_start_transcription_calls_feedback(self):
        # Stub UI elements retrieval to empty list
        self.widget.get_transcription_ui_elements = MagicMock(
            return_value=["ui1", "ui2"]
        )
        # Stub spinner and progress to return True
        self.widget.feedback_manager.start_spinner.return_value = True
        # Call method
        # The following should not raise
        self.widget.start_transcription()
        # Verify UI busy and spinner/progress invoked
        self.widget.feedback_manager.set_ui_busy.assert_called_with(
            True, ["ui1", "ui2"]
        )
        self.widget.feedback_manager.start_spinner.assert_called_with(
            "transcribe")
        # At least called for transcription progress
        self.widget.feedback_manager.start_progress.assert_called()

    def test_transcription_with_no_recording_selected(self):
        # No current recording
        self.widget.current_recording_data = None
        with patch("app.MainTranscriptionWidget.show_error_message") as mock_err:
            self.widget.start_transcription()
            mock_err.assert_called()
        # Feedback not started
        self.widget.feedback_manager.set_ui_busy.assert_not_called()
        self.widget.feedback_manager.start_spinner.assert_not_called()

    def test_transcription_progress_updates(self):
        # Provide a fake BusyGuard-like object
        guard = MagicMock()
        self.widget.transcription_guard = guard
        # With numeric chunk info
        self.widget.on_transcription_progress("Processing chunk 2/5...")
        guard.update_progress.assert_called_with(40, "Processing chunk 2/5...")
        guard.update_progress.reset_mock()
        # Without numeric info
        self.widget.on_transcription_progress("Preparing audio")
        guard.update_progress.assert_called_with(0, "Preparing audio")


@unittest.skipUnless(HAVE_CONTROL, "PyQt6 or ControlPanelWidget not available")
class TestControlPanelWidgetFeedback(unittest.TestCase):
    def setUp(self):
        self.widget = ControlPanelWidget.__new__(ControlPanelWidget)
        # Stub feedback_manager
        self.widget.feedback_manager = MagicMock()
        # Stub UI elements and methods
        self.widget.youtube_url_field = MagicMock()
        self.widget.youtube_url_field.text.return_value = "http://test"
        self.widget.get_youtube_ui_elements = MagicMock(
            return_value=["btn1", "btn2"])
        # Patch URL validation and filesystem
        patcher_url = patch(
            "app.ControlPanelWidget.validate_url", return_value=True)
        patcher_exists = patch("os.path.exists", return_value=True)
        patcher_api = patch(
            "app.ControlPanelWidget.get_api_key", return_value="key")
        self.addCleanup(patcher_url.stop)
        self.addCleanup(patcher_exists.stop)
        self.addCleanup(patcher_api.stop)
        patcher_url.start()
        patcher_exists.start()
        patcher_api.start()

    def test_submit_youtube_url_triggers_progress(self):
        # Stub start_progress
        self.widget.feedback_manager.start_progress = MagicMock()
        # Call method
        self.widget.submit_youtube_url()
        # Should call set_ui_busy(True) for YouTube UI elements
        self.widget.feedback_manager.set_ui_busy.assert_called_with(
            True, ["btn1", "btn2"]
        )
        # Should start progress with 'youtube_download'
        args, _ = self.widget.feedback_manager.start_progress.call_args
        self.assertEqual(args[0], "youtube_download")

    def test_youtube_submit_with_empty_url(self):
        self.widget.youtube_url_field.text.return_value = "  "
        with patch("app.ControlPanelWidget.show_error_message") as mock_err:
            self.widget.submit_youtube_url()
            mock_err.assert_called()
        self.widget.feedback_manager.start_progress.assert_not_called()

    def test_youtube_submit_with_invalid_url(self):
        self.widget.youtube_url_field.text.return_value = "not-a-url"
        with patch("app.ControlPanelWidget.validate_url", return_value=False), \
             patch("app.ControlPanelWidget.show_error_message") as mock_err:
            self.widget.submit_youtube_url()
            mock_err.assert_called()
        self.widget.feedback_manager.start_progress.assert_not_called()

    def test_youtube_download_cancellation(self):
        t = MagicMock()
        t.isRunning.return_value = True
        self.widget.youtube_download_thread = t
        self.widget.cancel_youtube_download()
        t.cancel.assert_called_once()
        self.widget.feedback_manager.show_status.assert_called()

    def test_youtube_progress_percentage_extraction(self):
        self.widget.yt_progress_id = "youtube_download"
        self.widget.on_youtube_progress("Downloading: 85%")
        self.widget.feedback_manager.update_progress.assert_called_with(
            "youtube_download", 85, "Downloading: 85%"
        )

    def test_youtube_download_error_recovery(self):
        # Set active progress ids to verify cleanup
        self.widget.yt_progress_id = "youtube_download"
        self.widget.transcoding_progress_id = "transcoding"
        with patch("app.ControlPanelWidget.show_error_message") as mock_err:
            self.widget.on_error("boom")
            mock_err.assert_called()
        # Progress closed
        self.widget.feedback_manager.close_progress.assert_any_call("youtube_download")
        self.widget.feedback_manager.close_progress.assert_any_call("transcoding")
