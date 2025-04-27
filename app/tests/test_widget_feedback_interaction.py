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
