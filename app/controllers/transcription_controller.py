"""Transcription controller for handling transcription process."""

import logging
import os
from typing import Dict, Any, Optional, Callable

from PyQt6.QtCore import QObject, pyqtSignal

from app.models.recording import Recording
from app.models.view_mode import ViewMode
from app.ui_utils.busy_guard import BusyGuard
from app.threads.TranscriptionThread import TranscriptionThread
from app.ThreadManager import ThreadManager
from app.secure import get_api_key
from app.constants import ERROR_INVALID_FILE, SUCCESS_TRANSCRIPTION

logger = logging.getLogger('transcribrr')


class TranscriptionController(QObject):
    """Controller for handling transcription process."""

    # Signals
    transcription_process_started = pyqtSignal()
    transcription_process_completed = pyqtSignal(str)  # Emits final transcript text
    transcription_process_stopped = pyqtSignal()
    status_update = pyqtSignal(str)  # Generic status update signal
    recording_status_updated = pyqtSignal(int, dict)  # Signal for recording updates (ID, data)

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.transcription_thread = None

    def start(self, recording: Recording, config: Dict[str, Any], busy_guard_callback: Callable) -> bool:
        """
        Start the transcription process.

        Args:
            recording: The Recording object to transcribe
            config: Configuration dictionary with transcription settings
            busy_guard_callback: Function that returns a BusyGuard instance

        Returns:
            bool: True if transcription started successfully, False otherwise
        """
        # Validate recording
        if not self._validate_inputs(recording):
            return False

        # Build thread arguments
        thread_args = self._build_thread_args(recording, config)
        if not thread_args:
            return False

        # Emit signal
        self.status_update.emit("Starting transcription...")
        self.transcription_process_started.emit()

        # Create and launch transcription thread
        self.transcription_thread = TranscriptionThread(**thread_args)

        # Connect signals
        self.transcription_thread.completed.connect(
            lambda transcript: self._on_transcription_completed(recording, transcript))
        self.transcription_thread.update_progress.connect(self._on_transcription_progress)
        self.transcription_thread.error.connect(self._on_transcription_error)
        self.transcription_thread.finished.connect(self._on_transcription_finished)

        # Register thread with ThreadManager
        ThreadManager.instance().register_thread(self.transcription_thread)

        # Start thread
        self.transcription_thread.start()

        return True

    def _validate_inputs(self, recording: Recording) -> bool:
        """Validate transcription inputs."""
        if not recording:
            return False

        # Validate file path
        file_path = recording.file_path
        if not file_path or not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return False

        # Validate file size
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > 300:  # 300MB limit
            logger.error(f"File too large: {file_size_mb:.1f}MB")
            return False

        return True

    def _build_thread_args(self, recording: Recording, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Build arguments for the transcription thread."""
        # Extract config values
        transcription_method = config.get('transcription_method', 'local')
        transcription_quality = config.get('transcription_quality', 'openai/whisper-large-v3')
        speaker_detection_enabled = config.get('speaker_detection_enabled', False)
        hardware_acceleration_enabled = config.get('hardware_acceleration_enabled', True)
        language = config.get('transcription_language', 'english')

        # Get API keys if needed
        openai_api_key = None
        hf_auth_key = None

        if transcription_method == 'api':
            openai_api_key = get_api_key("OPENAI_API_KEY")
            if not openai_api_key:
                logger.error("OpenAI API key missing for API transcription")
                return None

        if speaker_detection_enabled:
            hf_auth_key = get_api_key("HF_API_KEY")
            if not hf_auth_key:
                logger.error("Hugging Face API key missing for speaker detection")
                return None

        # Build thread arguments
        return {
            'file_path': recording.file_path,
            'transcription_quality': transcription_quality,
            'speaker_detection_enabled': speaker_detection_enabled,
            'hf_auth_key': hf_auth_key,
            'language': language,
            'transcription_method': transcription_method,
            'openai_api_key': openai_api_key,
            'hardware_acceleration_enabled': hardware_acceleration_enabled,
        }

    def _on_transcription_progress(self, message: str) -> None:
        """Handle progress updates from transcription thread."""
        self.status_update.emit(message)  # Forward to status bar

    def _on_transcription_completed(self, recording: Recording, transcript: str) -> None:
        """Handle the completed transcription."""
        if not recording:
            return  # Recording deselected during process

        recording_id = recording.id
        formatted_field = 'raw_transcript_formatted'
        raw_field = 'raw_transcript'

        # Check if result contains speaker labels
        is_formatted = transcript.strip().startswith("SPEAKER_") and ":" in transcript[:20]

        if is_formatted:
            db_value = f"<pre>{transcript}</pre>"
        else:
            db_value = transcript  # Store raw text if not formatted

        self.status_update.emit("Transcription complete. Saving...")

        # Define callback for when database update completes
        def on_update_complete():
            # Emit signals
            self.status_update.emit(SUCCESS_TRANSCRIPTION)
            self.transcription_process_completed.emit(transcript)

            # Emit signal to update UI in other components
            status_updates = {
                'has_transcript': True,
                raw_field: transcript,
                formatted_field: db_value if is_formatted else None
            }
            self.recording_status_updated.emit(recording_id, status_updates)

        # Save the raw transcript to the database
        update_data = {raw_field: transcript}
        if is_formatted:
            update_data[formatted_field] = db_value
        else:
            update_data[formatted_field] = None

        self.db_manager.update_recording(recording_id, on_update_complete, **update_data)

    def _on_transcription_error(self, error_message: str) -> None:
        """Handle transcription errors."""
        self.status_update.emit(f"Transcription failed: {error_message}")

    def _on_transcription_finished(self) -> None:
        """Called when transcription thread finishes, regardless of success."""
        # Clean up thread reference
        self.transcription_thread = None
        logger.info("Transcription thread finished.")

        # Inform listeners that the UI is ready again
        self.status_update.emit("Ready")

    def cancel(self) -> None:
        """Cancel current transcription if running."""
        if self.transcription_thread and self.transcription_thread.isRunning():
            logger.info("Canceling transcription...")
            self.transcription_thread.cancel()
            self.status_update.emit("Canceling transcription...")
