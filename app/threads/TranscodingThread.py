from PyQt6.QtCore import QThread, pyqtSignal
from pydub import AudioSegment
import os
from app.constants import get_recordings_dir
from moviepy.editor import VideoFileClip
import logging
from threading import Lock
from app.utils import is_video_file, is_audio_file

# Configure logging
logger = logging.getLogger("transcribrr")


class TranscodingThread(QThread):
    update_progress = pyqtSignal(str)
    completed = pyqtSignal(
        str
    )  # Now emits a single file path string, not an object/list
    error = pyqtSignal(str)

    def __init__(self, file_path=None, target_format="mp3", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.file_path = file_path
        self.target_format = target_format
        # Configure user recordings directory
        self.recordings_dir = get_recordings_dir()

        # Cancellation support
        self._is_canceled = False
        self._lock = Lock()

    def cancel(self):
        with self._lock:
            if not self._is_canceled:
                logger.info("Cancellation requested for transcoding thread.")
                self._is_canceled = True
                self.requestInterruption()  # Use QThread's built-in interruption
                # Note: Can't easily interrupt underlying transcoding operations
                # This will primarily prevent starting new operations

    def is_canceled(self):
        # Check both the custom flag and QThread's interruption status
        with self._lock:
            return self._is_canceled or self.isInterruptionRequested()

    def run(self):
        temp_files = []  # Track temporary files for cleanup in case of cancellation
        try:
            if self.is_canceled():
                self.update_progress.emit(
                    "Transcoding cancelled before starting.")
                return

            # Validate input file exists
            if not self.file_path:
                raise ValueError("No file path provided for transcoding.")

            if not os.path.exists(self.file_path):
                raise FileNotFoundError(f"File not found: {self.file_path}")

            # Validate output directory
            recordings_dir = self.recordings_dir
            try:
                os.makedirs(recordings_dir, exist_ok=True)
            except (PermissionError, OSError) as e:
                raise RuntimeError(f"Cannot create recordings directory: {e}")

            # Ensure we have write permission to the directory
            if not os.access(recordings_dir, os.W_OK):
                raise PermissionError(
                    f"No write permission to recordings directory: {recordings_dir}"
                )

            # Check file type and process accordingly
            if is_audio_file(self.file_path):
                self.update_progress.emit("Transcoding audio file...")
                self.transcode_audio(self.file_path, recordings_dir)
            elif is_video_file(self.file_path):
                self.update_progress.emit(
                    "Extracting audio from video file...")
                self.extract_audio_from_video(self.file_path, recordings_dir)
            else:
                raise ValueError(
                    f"Unsupported file type for transcoding: {os.path.basename(self.file_path)}"
                )

        except FileNotFoundError as e:
            if not self.is_canceled():
                self.error.emit(f"File not found: {e}")
                logger.error(f"Transcoding file not found: {e}", exc_info=True)
            else:
                self.update_progress.emit(
                    "Transcoding cancelled during file check.")

        except PermissionError as e:
            if not self.is_canceled():
                self.error.emit(f"Permission error: {e}")
                logger.error(
                    f"Transcoding permission error: {e}", exc_info=True)
            else:
                self.update_progress.emit(
                    "Transcoding cancelled during permission check."
                )

        except OSError as e:
            if not self.is_canceled():
                from app.secure import redact

                safe_err = redact(str(e))
                self.error.emit(f"File system error: {safe_err}")
                logger.error(f"Transcoding OS error: {e}", exc_info=True)
            else:
                self.update_progress.emit(
                    "Transcoding cancelled during file operation."
                )

        except ValueError as e:
            if not self.is_canceled():
                self.error.emit(f"Invalid input: {e}")
                logger.error(f"Transcoding value error: {e}", exc_info=True)
            else:
                self.update_progress.emit(
                    "Transcoding cancelled during validation.")

        except RuntimeError as e:
            if not self.is_canceled():
                self.error.emit(f"Processing error: {e}")
                logger.error(f"Transcoding runtime error: {e}", exc_info=True)
            else:
                self.update_progress.emit(
                    "Transcoding cancelled during processing.")

        except Exception as e:
            if not self.is_canceled():
                from app.secure import redact

                safe_err = redact(str(e))
                self.error.emit(f"Unexpected error: {safe_err}")
                logger.error(
                    f"Transcoding unexpected error: {e}", exc_info=True)
            else:
                self.update_progress.emit(
                    "Transcoding cancelled during processing.")
        finally:
            # Clean up any temporary files if thread was cancelled
            try:
                # Always attempt to clean up temp files, regardless of cancellation state
                for temp_file in temp_files:
                    if temp_file and os.path.exists(temp_file):
                        try:
                            os.remove(temp_file)
                            logger.info(
                                f"Cleaned up temporary file: {temp_file}")
                        except Exception as cleanup_error:
                            logger.warning(
                                f"Failed to clean up temporary file {temp_file}: {cleanup_error}"
                            )
            except Exception as e:
                logger.error(
                    f"Error during post-processing cleanup: {e}", exc_info=True
                )

            logger.info("Transcoding thread finished execution.")

    def transcode_audio(self, source_path, target_dir):
        self.update_progress.emit("Transcoding audio file...")
        target_file_path = self.generate_unique_target_path(
            target_dir, self.target_format
        )
        self.reencode_audio(source_path, target_file_path)

        # Optionally remove the original source file
        if os.path.exists(target_file_path):
            os.remove(source_path)

        self.update_progress.emit("Audio transcoding completed successfully.")
        self.completed.emit(target_file_path)

    def extract_audio_from_video(self, video_path, target_dir):
        self.update_progress.emit("Extracting audio from video...")
        audio_path = self.generate_unique_target_path(
            target_dir, "mp3", audio_only=True
        )

        try:
            with VideoFileClip(video_path) as video:
                if video.audio is None:
                    raise ValueError(
                        "The selected video file contains no audio track.")
                video.audio.write_audiofile(audio_path, logger=None)
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise RuntimeError(f"Failed to extract audio: {e}") from e

        # Optionally remove the original video file
        if os.path.exists(audio_path):
            os.remove(video_path)

        self.update_progress.emit("Audio extraction completed successfully.")
        self.completed.emit(audio_path)

    def generate_unique_target_path(self, target_dir, target_format, audio_only=False):
        base_name = os.path.basename(self.file_path)
        name, _ = os.path.splitext(base_name)
        if audio_only:
            name += "_extracted_audio"
        counter = 1
        target_file_path = os.path.join(target_dir, f"{name}.{target_format}")
        while os.path.exists(target_file_path):
            target_file_path = os.path.join(
                target_dir, f"{name}_{counter}.{target_format}"
            )
            counter += 1
        return target_file_path

    def reencode_audio(self, source_path, target_path):
        self.update_progress.emit("Re-encoding audio...")
        audio = AudioSegment.from_file(source_path)
        audio.export(target_path, format=self.target_format)

    def handle_error(self, error_object):
        logger.error("Error in TranscodingThread", exc_info=True)
        self.error.emit(str(error_object))
