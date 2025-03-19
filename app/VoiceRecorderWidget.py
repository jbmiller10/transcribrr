import sys
import os
import pyaudio
from pydub import AudioSegment
import wave
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout,
    QSlider, QStyle, QMessageBox, QProgressDialog, QFileDialog, QLineEdit
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
from app.utils import resource_path, format_time_duration

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class AudioLevelMeter(QWidget):
    """Audio level visualization widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(40)
        self.level = 0
        self.peak_level = 0
        self.decay_rate = 0.05  # Level decay rate when not recording
        self.setStyleSheet("background-color: transparent;")

        # Start decay timer
        self.decay_timer = QTimer(self)
        self.decay_timer.timeout.connect(self.decay_levels)
        self.decay_timer.start(50)  # 50ms updates

    def set_level(self, level):
        """Set the current audio level (0.0 to 1.0)."""
        self.level = min(max(level, 0.0), 1.0)
        self.peak_level = max(self.peak_level, self.level)
        self.update()

    def decay_levels(self):
        """Gradually decrease levels for smooth visual effect."""
        if self.level > 0:
            self.level = max(0, self.level - self.decay_rate)
        if self.peak_level > 0:
            self.peak_level = max(0, self.peak_level - self.decay_rate / 4)  # Peak decays slower
        self.update()

    def paintEvent(self, event):
        """Draw the audio level visualization."""
        from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QBrush

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)  # Fixed enum

        width = self.width() - 4  # Margin
        height = self.height() - 4  # Margin

        # Background
        painter.setPen(Qt.PenStyle.NoPen)  # Fixed enum
        painter.setBrush(QColor(50, 50, 50, 30))
        painter.drawRoundedRect(2, 2, width, height, 6, 6)

        # Level fill
        if self.level > 0:
            # Create gradient
            gradient = QLinearGradient(0, 0, width, 0)
            gradient.setColorAt(0, QColor("#4CAF50"))  # Green
            gradient.setColorAt(0.7, QColor("#FFC107"))  # Yellow
            gradient.setColorAt(0.9, QColor("#F44336"))  # Red

            fill_width = int(width * self.level)
            painter.setBrush(QBrush(gradient))
            painter.drawRoundedRect(2, 2, fill_width, height, 6, 6)

        # Peak indicator
        if self.peak_level > 0:
            peak_x = int(width * self.peak_level)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawLine(peak_x, 2, peak_x, height + 2)


class RecordingThread(QThread):
    """Thread for handling audio recording in the background."""

    update_level = pyqtSignal(float)
    update_time = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, audio_instance, format, channels, rate, frames_per_buffer, parent=None):
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

        # For level metering
        self.level_timer = QTimer()
        self.level_timer.moveToThread(self)
        self.level_timer.timeout.connect(self.update_elapsed_time)

    def run(self):
        """Main recording loop."""
        try:
            self.stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.rate,
                input=True,
                frames_per_buffer=self.frames_per_buffer
            )

            # Start timer for elapsed time updates
            self.level_timer.start(1000)  # 1 second updates

            # Reset elapsed time
            self.elapsed_time = 0

            while self.is_recording:
                if not self.is_paused:
                    try:
                        data = self.stream.read(self.frames_per_buffer, exception_on_overflow=False)
                        self.frames.append(data)

                        # Calculate audio level for visualization
                        if len(data) > 0:
                            audio_array = np.frombuffer(data, dtype=np.int16)
                            max_amplitude = np.max(np.abs(audio_array))
                            normalized_level = max_amplitude / 32768.0  # Normalize to 0.0-1.0
                            self.update_level.emit(normalized_level)
                    except Exception as e:
                        self.error.emit(f"Error reading audio: {e}")
                else:
                    # When paused, sleep to prevent high CPU usage
                    time.sleep(0.1)

            # Clean up the stream
            self.level_timer.stop()
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None

        except Exception as e:
            self.error.emit(f"Recording error: {e}")
            logging.error(f"Recording error: {e}", exc_info=True)

    def update_elapsed_time(self):
        """Update the elapsed time counter."""
        if self.is_recording and not self.is_paused:
            self.elapsed_time += 1
            self.update_time.emit(self.elapsed_time)

    def pauseRecording(self):
        """Pause the recording."""
        if self.is_recording:
            self.is_paused = True

    def resumeRecording(self):
        """Resume the recording after pausing."""
        if self.is_recording:
            self.is_paused = False

    def startRecording(self):
        """Start the recording thread."""
        self.is_recording = True
        self.is_paused = False
        self.frames.clear()
        self.elapsed_time = 0
        self.start()

    def stopRecording(self):
        """Stop the recording thread."""
        self.is_recording = False
        self.is_paused = False
        self.level_timer.stop()

    def saveRecording(self, filename=None):
        """
        Save the recorded audio to a file.

        Args:
            filename (str, optional): Full path for saving the file.
                                     If None, generates a timestamped filename.

        Returns:
            str: Path to the saved audio file
        """
        if not self.frames:
            self.error.emit("No audio data to save")
            return None

        recordings_dir = os.path.join(os.getcwd(), "Recordings")
        os.makedirs(recordings_dir, exist_ok=True)

        if filename is None:
            timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            filename = os.path.join(recordings_dir, f"Recording-{timestamp}.mp3")

        # Write to a temporary WAV file first
        temp_wav = tempfile.NamedTemporaryFile(suffix='.wav', delete=False).name

        try:
            # Save as WAV
            wf = wave.open(temp_wav, 'wb')
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.audio.get_sample_size(self.format))
            wf.setframerate(self.rate)
            wf.writeframes(b''.join(self.frames))
            wf.close()

            # Convert to MP3
            audio = AudioSegment.from_wav(temp_wav)
            audio.export(filename, format="mp3", bitrate="192k")

            # Clean up temporary file
            os.remove(temp_wav)

            self.frames.clear()
            return filename

        except Exception as e:
            self.error.emit(f"Error saving recording: {e}")
            logging.error(f"Error saving recording: {e}", exc_info=True)

            # Clean up
            if os.path.exists(temp_wav):
                try:
                    os.remove(temp_wav)
                except:
                    pass

            return None


class VoiceRecorderWidget(QWidget):
    """Widget for recording audio from microphone."""

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
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.updateTimer)

    def initUI(self):
        """Initialize the user interface."""
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)

        # Instructions
        instruction_label = QLabel("Click the button below to start recording from your microphone")
        instruction_label.setAlignment(Qt.AlignmentFlag.AlignCenter)  # Fixed enum
        instruction_label.setStyleSheet("color: #666; font-style: italic;")
        self.layout.addWidget(instruction_label)

        # Level meter
        self.level_meter = AudioLevelMeter()
        self.layout.addWidget(self.level_meter)

        # Timer display
        self.timerLabel = QLabel("00:00:00")
        self.timerLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)  # Fixed enum
        self.timerLabel.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.layout.addWidget(self.timerLabel)

        # Status label
        self.statusLabel = QLabel("Ready to record")
        self.statusLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)  # Fixed enum
        self.layout.addWidget(self.statusLabel)

        # Record button with SVG icons
        record_button_layout = QHBoxLayout()
        record_button_svg_files = {
            'record': resource_path('icons/record.svg'),
            'pause': resource_path('icons/pause.svg'),
        }

        self.recordButton = SVGToggleButton(record_button_svg_files)
        self.recordButton.setFixedSize(80, 80)
        self.recordButton.clicked.connect(self.toggleRecording)
        record_button_layout.addWidget(self.recordButton, 0, Qt.AlignmentFlag.AlignCenter)  # Fixed enum

        self.layout.addLayout(record_button_layout)

        # Save and Delete buttons in a horizontal layout
        buttonLayout = QHBoxLayout()

        self.saveButton = QPushButton("Save")
        self.saveButton.setIcon(QIcon(resource_path('icons/save.svg')))
        self.saveButton.clicked.connect(self.saveRecording)
        self.saveButton.setEnabled(False)
        buttonLayout.addWidget(self.saveButton)

        self.deleteButton = QPushButton("Discard")
        self.deleteButton.setIcon(QIcon(resource_path('icons/delete.svg')))
        self.deleteButton.clicked.connect(self.deleteRecording)
        self.deleteButton.setEnabled(False)
        buttonLayout.addWidget(self.deleteButton)

        self.layout.addLayout(buttonLayout)

    def initAudio(self):
        """Initialize audio parameters."""
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 44100
        self.frames_per_buffer = 4096

        try:
            self.audio = pyaudio.PyAudio()

            # Check available input devices
            info = self.audio.get_host_api_info_by_index(0)
            num_devices = info.get('deviceCount')

            # Log available input devices for debugging
            for i in range(num_devices):
                if self.audio.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels') > 0:
                    logging.info(
                        f"Input Device {i}: {self.audio.get_device_info_by_host_api_device_index(0, i).get('name')}")

        except Exception as e:
            logging.error(f"Error initializing audio: {e}", exc_info=True)
            self.statusLabel.setText("Error: Could not initialize audio system")
            self.recordButton.setEnabled(False)

    def toggleRecording(self):
        """Toggle recording state (start/pause/resume)."""
        if not self.is_recording:
            self.startRecording()
        elif self.is_paused:
            self.resumeRecording()
        else:
            self.pauseRecording()

    def startRecording(self):
        """Start a new recording."""
        self.is_recording = True
        self.is_paused = False
        self.recordButton.set_svg('pause')
        self.statusLabel.setText("Recording...")
        self.saveButton.setEnabled(True)
        self.deleteButton.setEnabled(True)

        try:
            self.recording_thread = RecordingThread(
                self.audio, self.format, self.channels, self.rate, self.frames_per_buffer
            )
            self.recording_thread.update_level.connect(self.level_meter.set_level)
            self.recording_thread.update_time.connect(self.updateTimerValue)
            self.recording_thread.error.connect(self.handleRecordingError)
            self.recording_thread.startRecording()
            self.timer.start(100)  # Update UI frequently for smoother appearance

            # Emit signal that recording has started
            self.recordingStarted.emit()

        except Exception as e:
            self.handleRecordingError(f"Failed to start recording: {e}")

    def pauseRecording(self):
        """Pause the current recording."""
        if self.recording_thread:
            self.is_paused = True
            self.recordButton.set_svg('record')
            self.statusLabel.setText("Recording paused")
            self.recording_thread.pauseRecording()
            self.timer.stop()

    def resumeRecording(self):
        """Resume a paused recording."""
        if self.recording_thread:
            self.is_paused = False
            self.recordButton.set_svg('pause')
            self.statusLabel.setText("Recording...")
            self.recording_thread.resumeRecording()
            self.timer.start(100)

    def saveRecording(self):
        """Save the current recording."""
        if self.recording_thread:
            # Stop recording if it's still active
            if self.is_recording:
                self.is_recording = False
                self.is_paused = False
                self.recordButton.set_svg('record')
                self.recording_thread.stopRecording()
                self.recording_thread.wait()
                self.timer.stop()

            # Ask user for filename
            recordings_dir = os.path.join(os.getcwd(), "Recordings")
            os.makedirs(recordings_dir, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            default_name = f"Recording-{timestamp}.mp3"

            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save Recording", os.path.join(recordings_dir, default_name),
                "MP3 Files (*.mp3);;All Files (*)"
            )

            if file_path:
                # Ensure the extension is .mp3
                if not file_path.lower().endswith('.mp3'):
                    file_path += '.mp3'

                # Show a progress dialog for longer recordings
                if self.elapsed_time > 10:  # Only for recordings longer than 10 seconds
                    progress = QProgressDialog("Saving recording...", None, 0, 100, self)
                    progress.setWindowTitle("Saving Recording")
                    progress.setWindowModality(Qt.WindowModality.WindowModal)  # Fixed enum
                    progress.setValue(10)
                    QApplication.processEvents()

                try:
                    file_name = self.recording_thread.saveRecording(file_path)

                    if file_name:
                        self.statusLabel.setText("Recording saved")
                        self.resetUI()
                        self.recordingCompleted.emit(file_name)
                    else:
                        self.statusLabel.setText("Error: Failed to save recording")

                    # Close progress dialog if it was shown
                    if self.elapsed_time > 10:
                        progress.setValue(100)

                except Exception as e:
                    self.handleRecordingError(f"Error saving recording: {e}")
            else:
                # User cancelled the save dialog
                self.statusLabel.setText("Save cancelled")

    def deleteRecording(self):
        """Delete the current recording without saving."""
        if self.recording_thread:
            # Stop recording if it's still active
            if self.is_recording:
                self.is_recording = False
                self.is_paused = False
                self.recordButton.set_svg('record')
                self.recording_thread.stopRecording()
                self.recording_thread.wait()
                self.timer.stop()

            # Clear the recorded frames
            if hasattr(self.recording_thread, 'frames'):
                self.recording_thread.frames.clear()

            self.statusLabel.setText("Recording discarded")
            self.resetUI()

    def resetUI(self):
        """Reset the UI to initial state."""
        self.elapsed_time = 0
        self.timerLabel.setText("00:00:00")
        self.recordButton.set_svg('record')
        self.saveButton.setEnabled(False)
        self.deleteButton.setEnabled(False)
        self.is_recording = False
        self.is_paused = False
        self.level_meter.set_level(0)

    def updateTimer(self):
        """Update the timer display."""
        if self.is_recording and not self.is_paused:
            time_str = format_time_duration(self.elapsed_time)
            self.timerLabel.setText(time_str)

    def updateTimerValue(self, seconds):
        """Update timer value from recording thread."""
        self.elapsed_time = seconds
        self.updateTimer()

    def handleRecordingError(self, error_message):
        """Handle recording errors."""
        logging.error(f"Recording error: {error_message}")
        self.statusLabel.setText(f"Error: {error_message}")
        self.recordingError.emit(error_message)

        # Reset the UI state
        self.resetUI()

        # Show error message to user
        QMessageBox.critical(self, "Recording Error",
                             f"An error occurred during recording:\n{error_message}")


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