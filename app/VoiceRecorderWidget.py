import sys
import os
import shutil
try:
    import pyaudio  # type: ignore
except Exception:  # PyAudio may be unavailable on some platforms (e.g., macOS app build)
    pyaudio = None  # type: ignore
from pydub import AudioSegment
import wave
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QMessageBox,
    QProgressDialog,
    QFileDialog,
)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt, QSize
from PyQt6.QtGui import QIcon, QColor
import datetime
import logging
from collections import deque
import tempfile
import numpy as np
import time
from app.SVGToggleButton import SVGToggleButton
from app.path_utils import resource_path
from app.utils import format_time_duration
from app.ThreadManager import ThreadManager
from app.constants import get_recordings_dir

# Logging configuration should be done in main.py, not here
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("transcribrr")


class AudioLevelMeter(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(40)
        self.level = 0
        self.peak_level = 0
        self.decay_rate = 0.05  # Level decay rate when not recording
        self.setStyleSheet("background-color: transparent;")

        self.decay_timer = QTimer(self)
        self.decay_timer.timeout.connect(self.decay_levels)
        self.decay_timer.start(50)

    def set_level(self, level):
        self.level = min(max(level, 0.0), 1.0)
        self.peak_level = max(self.peak_level, self.level)
        self.update()

    def decay_levels(self):
        if self.level > 0:
            self.level = max(0, self.level - self.decay_rate)
        if self.peak_level > 0:
            self.peak_level = max(
                0, self.peak_level - self.decay_rate / 4
            )  # Peak decays slower
        self.update()

    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter, QLinearGradient, QBrush

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)  # Fixed enum

        width = self.width() - 4  # Margin
        height = self.height() - 4  # Margin

        painter.setPen(Qt.PenStyle.NoPen)  # Fixed enum
        painter.setBrush(QColor(50, 50, 50, 30))
        painter.drawRoundedRect(2, 2, width, height, 6, 6)

        if self.level > 0:
            # Create gradient
            gradient = QLinearGradient(0, 0, width, 0)
            gradient.setColorAt(0, QColor("#4CAF50"))  # Green
            gradient.setColorAt(0.7, QColor("#FFC107"))  # Yellow
            gradient.setColorAt(0.9, QColor("#F44336"))  # Red

            fill_width = int(width * self.level)
            painter.setBrush(QBrush(gradient))
            painter.drawRoundedRect(2, 2, fill_width, height, 6, 6)

        if self.peak_level > 0:
            peak_x = int(width * self.peak_level)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawLine(peak_x, 2, peak_x, height + 2)


class RecordingThread(QThread):

    update_level = pyqtSignal(float)
    update_time = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(
        self, audio_instance, format, channels, rate, frames_per_buffer, parent=None
    ):
        super().__init__(parent)
        self.audio = audio_instance
        self.format = format
        self.channels = channels
        self.rate = rate
        self.frames_per_buffer = frames_per_buffer
        self.frames = deque()
        self.is_recording = False
        self.is_paused = False
        self.elapsed_time = 0
        self.stream = None

        # Don't create timers here - we'll handle time tracking differently

    def run(self):
        try:
            # Initialize audio stream with proper error handling
            try:
                self.stream = self.audio.open(
                    format=self.format,
                    channels=self.channels,
                    rate=self.rate,
                    input=True,
                    frames_per_buffer=self.frames_per_buffer,
                )
            except (KeyError, ValueError) as e:
                raise RuntimeError(
                    f"Failed to initialize audio stream with current settings: {e}"
                )
            except IOError as e:
                raise RuntimeError(f"Audio device error: {e}")
            except Exception as e:
                raise RuntimeError(
                    f"Unexpected error initializing audio stream: {e}")

            self.elapsed_time = 0
            last_time_update = time.time()

            # Main recording loop with robust error handling
            while self.is_recording:
                if not self.is_paused:
                    try:
                        # Read audio data with timeout protection
                        data = self.stream.read(
                            self.frames_per_buffer, exception_on_overflow=False
                        )
                        if not data:
                            logger.warning(
                                "Empty audio data received, possible device disconnection"
                            )
                            continue

                        self.frames.append(data)

                        # Calculate audio level for visualization
                        if len(data) > 0:
                            try:
                                audio_array = np.frombuffer(
                                    data, dtype=np.int16)
                                max_amplitude = (
                                    np.max(np.abs(audio_array))
                                    if len(audio_array) > 0
                                    else 0
                                )
                                normalized_level = (
                                    max_amplitude / 32768.0
                                )  # Normalize to 0.0-1.0
                                self.update_level.emit(normalized_level)
                            except Exception as viz_error:
                                # Non-critical error, just log it
                                logger.warning(
                                    f"Error calculating audio level: {viz_error}"
                                )

                        # Check if we need to update elapsed time (every second)
                        current_time = time.time()
                        if current_time - last_time_update >= 1.0:
                            self.elapsed_time += 1
                            self.update_time.emit(self.elapsed_time)
                            last_time_update = current_time

                    except IOError as e:
                        if "Input overflowed" in str(e):
                            # This is a non-critical error, just log and continue
                            logger.warning("Audio input overflow detected")
                            continue
                        elif "Device unavailable" in str(
                            e
                        ) or "Input underflowed" in str(e):
                            # Device might be temporarily unavailable
                            logger.warning(f"Audio device issue: {e}")
                            # Short sleep to avoid CPU spinning
                            time.sleep(0.1)
                            continue
                        else:
                            # Other IO errors might be more serious
                            self.error.emit(f"Audio device error: {e}")
                            logger.error(f"Audio IO error: {e}", exc_info=True)
                            # Short sleep before retrying
                            time.sleep(0.5)
                    except Exception as e:
                        self.error.emit(f"Error reading audio: {e}")
                        logger.error(
                            f"Audio processing error: {e}", exc_info=True)
                        # Short sleep before retrying
                        time.sleep(0.5)
                else:
                    # When paused, sleep to prevent high CPU usage
                    time.sleep(0.1)

        except Exception as e:
            from app.secure import redact

            safe_msg = redact(str(e))
            self.error.emit(f"Recording error: {safe_msg}")
            logger.error(f"Recording thread error: {e}", exc_info=True)
        finally:
            # Clean up resources properly in all cases
            try:
                if hasattr(self, "stream") and self.stream:
                    try:
                        self.stream.stop_stream()
                    except Exception as stop_error:
                        logger.warning(
                            f"Error stopping audio stream: {stop_error}")

                    try:
                        self.stream.close()
                    except Exception as close_error:
                        logger.warning(
                            f"Error closing audio stream: {close_error}")

                    self.stream = None
                    logger.debug("Audio stream properly closed")
            except Exception as cleanup_error:
                logger.error(
                    f"Error during audio stream cleanup: {cleanup_error}", exc_info=True
                )

            logger.info("Recording thread finished execution")

    # Time updates are now handled directly in the run method

    def pauseRecording(self):
        if self.is_recording:
            self.is_paused = True

    def resumeRecording(self):
        if self.is_recording:
            self.is_paused = False

    def startRecording(self):
        self.is_recording = True
        self.is_paused = False
        self.frames.clear()
        self.elapsed_time = 0
        self.start()

    def stopRecording(self):
        self.is_recording = False
        self.is_paused = False
        self.level_timer.stop()

    def saveRecording(self, filename=None):
        if not self.frames:
            self.error.emit("No audio data to save")
            return None

        recordings_dir = os.path.join(os.getcwd(), "Recordings")
        os.makedirs(recordings_dir, exist_ok=True)

        if filename is None:
            timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            filename = os.path.join(
                recordings_dir, f"Recording-{timestamp}.mp3")

        temp_wav_path = None
        temp_mp3_path = None

        final_path = filename

        try:
            # 1. Save raw audio to temp WAV file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
                temp_wav_path = tmp_wav.name
            logger.debug(f"Created temporary WAV path: {temp_wav_path}")

            wf = wave.open(temp_wav_path, "wb")
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.audio.get_sample_size(self.format))
            wf.setframerate(self.rate)
            wf.writeframes(b"".join(self.frames))
            wf.close()
            logger.debug(f"Saved raw audio to temporary WAV: {temp_wav_path}")

            # 2. Convert WAV to temp MP3 file
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_mp3:
                temp_mp3_path = tmp_mp3.name
            logger.debug(f"Created temporary MP3 path: {temp_mp3_path}")

            logger.debug(f"Converting {temp_wav_path} to {temp_mp3_path}")
            audio_segment = AudioSegment.from_wav(temp_wav_path)
            audio_segment.export(temp_mp3_path, format="mp3", bitrate="192k")
            logger.debug("Conversion to temporary MP3 successful.")

            # 3. Move MP3 to final destination
            logger.debug(f"Moving {temp_mp3_path} to {final_path}")
            shutil.move(temp_mp3_path, final_path)
            temp_mp3_path = None

            self.frames.clear()
            logger.info(f"Recording successfully saved to: {final_path}")
            return final_path

        except Exception as e:
            self.error.emit(f"Error saving recording: {e}")
            logger.error(f"Error saving recording: {e}", exc_info=True)
            return None

        finally:
            # Cleanup temp WAV
            if temp_wav_path and os.path.exists(temp_wav_path):
                try:
                    os.remove(temp_wav_path)
                    logger.debug(f"Cleaned up temp WAV: {temp_wav_path}")
                except Exception as cleanup_err:
                    logger.warning(
                        f"Failed to clean up temp WAV {temp_wav_path}: {cleanup_err}"
                    )
            # Cleanup temp MP3 if not moved
            if temp_mp3_path and os.path.exists(temp_mp3_path):
                try:
                    os.remove(temp_mp3_path)
                    logger.debug(f"Cleaned up temp MP3: {temp_mp3_path}")
                except Exception as cleanup_err:
                    logger.warning(
                        f"Failed to clean up temp MP3 {temp_mp3_path}: {cleanup_err}"
                    )


class VoiceRecorderWidget(QWidget):

    recordingCompleted = pyqtSignal(str)
    recordingStarted = pyqtSignal()
    recordingError = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()
        self.initAudio()
        self.recording_thread = None
        self.is_recording = False
        self.is_paused = False
        self.elapsed_time = 0
        # Use a single timer in the main thread for UI updates
        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self.updateUI)

    def initUI(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)

        # Instructions
        instruction_label = QLabel(
            "Click the button below to start recording from your microphone"
        )
        instruction_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter)  # Fixed enum
        instruction_label.setStyleSheet("color: #666; font-style: italic;")
        self.layout.addWidget(instruction_label)

        # Level meter
        self.level_meter = AudioLevelMeter()
        self.layout.addWidget(self.level_meter)

        # Timer display
        self.timerLabel = QLabel("00:00:00")
        self.timerLabel.setAlignment(
            Qt.AlignmentFlag.AlignCenter)  # Fixed enum
        self.timerLabel.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.layout.addWidget(self.timerLabel)

        # Status label
        self.statusLabel = QLabel("Ready to record")
        self.statusLabel.setAlignment(
            Qt.AlignmentFlag.AlignCenter)  # Fixed enum
        self.layout.addWidget(self.statusLabel)

        # Record button with SVG icons
        record_button_layout = QHBoxLayout()
        record_button_svg_files = {
            "record": resource_path("icons/record.svg"),
            "pause": resource_path("icons/pause.svg"),
        }

        self.recordButton = SVGToggleButton(record_button_svg_files)
        self.recordButton.setFixedSize(80, 80)
        self.recordButton.clicked.connect(self.toggleRecording)
        record_button_layout.addWidget(
            self.recordButton, 0, Qt.AlignmentFlag.AlignCenter
        )  # Fixed enum

        self.layout.addLayout(record_button_layout)

        # Save and Delete buttons in a horizontal layout
        buttonLayout = QHBoxLayout()
        buttonLayout.setAlignment(
            Qt.AlignmentFlag.AlignCenter)  # Center the buttons
        buttonLayout.setSpacing(20)  # Add spacing between buttons

        # Icon-only save button with transparent background
        self.saveButton = QPushButton()
        self.saveButton.setIcon(QIcon(resource_path("icons/save.svg")))
        self.saveButton.setIconSize(QSize(24, 24))  # Smaller icon size
        self.saveButton.setStyleSheet(
            """
            QPushButton {
                background-color: transparent;
                border: none;
            }
            QPushButton:hover {
                background-color: rgba(200, 200, 200, 30);
                border-radius: 4px;
            }
            QPushButton:pressed {
                background-color: rgba(150, 150, 150, 50);
            }
        """
        )
        self.saveButton.setToolTip("Save recording")
        self.saveButton.clicked.connect(self.saveRecording)
        self.saveButton.setEnabled(False)
        self.saveButton.setFixedSize(40, 40)
        buttonLayout.addWidget(self.saveButton)

        # Icon-only delete button with transparent background
        self.deleteButton = QPushButton()
        self.deleteButton.setIcon(QIcon(resource_path("icons/delete.svg")))
        self.deleteButton.setIconSize(QSize(24, 24))  # Smaller icon size
        self.deleteButton.setStyleSheet(
            """
            QPushButton {
                background-color: transparent;
                border: none;
            }
            QPushButton:hover {
                background-color: rgba(200, 200, 200, 30);
                border-radius: 4px;
            }
            QPushButton:pressed {
                background-color: rgba(150, 150, 150, 50);
            }
        """
        )
        self.deleteButton.setToolTip("Discard recording")
        self.deleteButton.clicked.connect(self.deleteRecording)
        self.deleteButton.setEnabled(False)
        self.deleteButton.setFixedSize(40, 40)
        buttonLayout.addWidget(self.deleteButton)

        self.layout.addLayout(buttonLayout)

    def initAudio(self):
        if pyaudio is None:
            logger.warning("PyAudio is not available; disabling recording UI.")
            self.statusLabel.setText("PyAudio not available; recording disabled")
            self.recordButton.setEnabled(False)
            self.saveButton.setEnabled(False)
            self.deleteButton.setEnabled(False)
            return

        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 44100
        self.frames_per_buffer = 4096

        try:
            self.audio = pyaudio.PyAudio()

            # Check available input devices
            info = self.audio.get_host_api_info_by_index(0)
            num_devices = info.get("deviceCount")

            # Log available input devices for debugging
            for i in range(num_devices):
                if (
                    self.audio.get_device_info_by_host_api_device_index(0, i).get(
                        "maxInputChannels"
                    )
                    > 0
                ):
                    logger.info(
                        f"Input Device {i}: {self.audio.get_device_info_by_host_api_device_index(0, i).get('name')}"
                    )

        except Exception as e:
            logger.error(f"Error initializing audio: {e}", exc_info=True)
            self.statusLabel.setText("Error: Could not initialize audio system")
            self.recordButton.setEnabled(False)

    def toggleRecording(self):
        if not self.is_recording:
            self.startRecording()
        elif self.is_paused:
            self.resumeRecording()
        else:
            self.pauseRecording()

    def startRecording(self):
        self.is_recording = True
        self.is_paused = False
        self.elapsed_time = 0
        self.recordButton.set_svg("pause")
        self.statusLabel.setText("Recording...")
        self.saveButton.setEnabled(True)
        self.deleteButton.setEnabled(True)

        # Update timer display immediately to show 00:00:00
        self.timerLabel.setText(format_time_duration(0))

        try:
            self.recording_thread = RecordingThread(
                self.audio,
                self.format,
                self.channels,
                self.rate,
                self.frames_per_buffer,
            )
            self.recording_thread.update_level.connect(
                self.level_meter.set_level)
            self.recording_thread.update_time.connect(self.updateTimerValue)
            self.recording_thread.error.connect(self.handleRecordingError)

            # Register with ThreadManager
            ThreadManager.instance().register_thread(self.recording_thread)
            self.recording_thread.startRecording()

            # Start UI update timer
            # Update UI frequently for smoother appearance
            self.ui_timer.start(100)

            # Emit signal that recording has started
            self.recordingStarted.emit()

        except Exception as e:
            self.handleRecordingError(f"Failed to start recording: {e}")

    def pauseRecording(self):
        if self.recording_thread:
            self.is_paused = True
            self.recordButton.set_svg("record")
            self.statusLabel.setText("Recording paused")
            self.recording_thread.pauseRecording()
            self.ui_timer.stop()

    def resumeRecording(self):
        if self.recording_thread:
            self.is_paused = False
            self.recordButton.set_svg("pause")
            self.statusLabel.setText("Recording...")
            self.recording_thread.resumeRecording()
            self.ui_timer.start(100)

    def saveRecording(self):
        if self.recording_thread:
            # Stop recording if it's still active
            if self.is_recording:
                self.is_recording = False
                self.is_paused = False
                self.recordButton.set_svg("record")
                self.recording_thread.stopRecording()
                self.recording_thread.wait()
                self.ui_timer.stop()

            # Ask user for filename
            # Ensure recordings directory exists
            os.makedirs(get_recordings_dir(), exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            default_name = f"Recording-{timestamp}.mp3"

            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Recording",
                os.path.join(get_recordings_dir(), default_name),
                "MP3 Files (*.mp3);;All Files (*)",
            )

            if file_path:
                # Ensure the extension is .mp3
                if not file_path.lower().endswith(".mp3"):
                    file_path += ".mp3"

                # Show a progress dialog for longer recordings
                if self.elapsed_time > 10:  # Only for recordings longer than 10 seconds
                    progress = QProgressDialog(
                        "Saving recording...", None, 0, 100, self
                    )
                    progress.setWindowTitle("Saving Recording")
                    progress.setWindowModality(
                        Qt.WindowModality.WindowModal
                    )  # Fixed enum
                    progress.setValue(10)
                    QApplication.processEvents()

                try:
                    file_name = self.recording_thread.saveRecording(file_path)

                    if file_name:
                        self.statusLabel.setText("Recording saved")
                        self.resetUI()
                        self.recordingCompleted.emit(file_name)
                    else:
                        self.statusLabel.setText(
                            "Error: Failed to save recording")

                    # Close progress dialog if it was shown
                    if self.elapsed_time > 10:
                        progress.setValue(100)

                except Exception as e:
                    self.handleRecordingError(f"Error saving recording: {e}")
            else:
                # User cancelled the save dialog
                self.statusLabel.setText("Save cancelled")

    def deleteRecording(self):
        if self.recording_thread:
            # Stop recording if it's still active
            if self.is_recording:
                self.is_recording = False
                self.is_paused = False
                self.recordButton.set_svg("record")
                self.recording_thread.stopRecording()
                self.recording_thread.wait()
                self.ui_timer.stop()

            # Clear the recorded frames
            if hasattr(self.recording_thread, "frames"):
                self.recording_thread.frames.clear()

            self.statusLabel.setText("Recording discarded")
            self.resetUI()

    def resetUI(self):
        self.elapsed_time = 0
        self.timerLabel.setText("00:00:00")
        self.recordButton.set_svg("record")
        self.saveButton.setEnabled(False)
        self.deleteButton.setEnabled(False)
        self.is_recording = False
        self.is_paused = False
        self.level_meter.set_level(0)

    def updateUI(self):
        # Update the timer display
        if self.is_recording:
            time_str = format_time_duration(self.elapsed_time)
            self.timerLabel.setText(time_str)

    def updateTimerValue(self, seconds):
        self.elapsed_time = seconds
        logger.debug(f"Received timer update: {seconds}s")
        # No need to force update - the regular UI timer will handle it

    def handleRecordingError(self, error_message):
        logger.error(f"Recording error: {error_message}")
        self.statusLabel.setText(f"Error: {error_message}")
        self.recordingError.emit(error_message)

        # Reset the UI state
        self.resetUI()

        # Show error message to user
        QMessageBox.critical(
            self,
            "Recording Error",
            f"An error occurred during recording:\n{error_message}",
        )


# For standalone testing
def main():
    app = QApplication(sys.argv)
    mainWindow = QWidget()
    mainWindow.setWindowTitle("Voice Recorder Test")
    mainWindow.resize(400, 300)

    layout = QVBoxLayout(mainWindow)
    recorderWidget = VoiceRecorderWidget()
    layout.addWidget(recorderWidget)

    mainWindow.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
