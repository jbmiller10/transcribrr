from PyQt6.QtCore import pyqtSignal, QSize, QPropertyAnimation, QEasingCurve, QTimer, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QMessageBox, QLineEdit,
    QApplication, QMainWindow, QVBoxLayout, QLabel, QProgressBar
)
import os
import sys
import logging
from app.utils import validate_url, resource_path
from app.threads.TranscodingThread import TranscodingThread
from app.threads.YouTubeDownloadThread import YouTubeDownloadThread
from app.VoiceRecorderWidget import VoiceRecorderWidget
from app.FileDropWidget import FileDropWidget

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class ControlPanelWidget(QWidget):
    uploaded_filepath = pyqtSignal(str)
    record_clicked = pyqtSignal()
    update_progress = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.transcoding_thread = None
        self.youtube_download_thread = None
        self.active_widget = None
        self.initUI()

    def initUI(self):
        """Initialize the UI components with improved layout and feedback widgets."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)

        # Progress bar for feedback (initially hidden)
        self.progress_container = QWidget()
        progress_layout = QVBoxLayout(self.progress_container)

        self.progress_label = QLabel("Processing...")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)  # Fixed enum
        progress_layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        self.progress_bar.setTextVisible(False)
        progress_layout.addWidget(self.progress_bar)

        main_layout.addWidget(self.progress_container)
        self.progress_container.setVisible(False)

        # YouTube container setup
        self.youtube_container = QWidget(self)
        youtube_layout = QHBoxLayout(self.youtube_container)

        self.youtube_url_field = QLineEdit(self.youtube_container)
        self.youtube_url_field.setPlaceholderText("Enter YouTube URL here")
        self.youtube_url_field.returnPressed.connect(self.submit_youtube_url)
        youtube_layout.addWidget(self.youtube_url_field)

        self.submit_youtube_url_button = QPushButton("Submit", self.youtube_container)
        self.submit_youtube_url_button.clicked.connect(self.submit_youtube_url)
        youtube_layout.addWidget(self.submit_youtube_url_button)

        main_layout.addWidget(self.youtube_container)
        self.youtube_container.setVisible(False)

        # Voice recorder widget setup
        self.voice_recorder_widget = VoiceRecorderWidget(self)
        main_layout.addWidget(self.voice_recorder_widget)
        self.voice_recorder_widget.recordingCompleted.connect(self.on_io_complete)
        self.voice_recorder_widget.setVisible(False)

        # File upload widget
        self.file_upload_layout = QHBoxLayout()
        self.file_upload_widget = FileDropWidget(self)
        self.file_upload_layout.addWidget(self.file_upload_widget)
        self.file_upload_widget.setVisible(False)
        self.file_upload_widget.fileDropped.connect(self.on_io_complete)

        main_layout.addLayout(self.file_upload_layout)

        # Button layout setup with improved styling
        button_layout = QHBoxLayout()

        self.upload_button = self.create_button('./icons/upload.svg', "Upload Local Audio/Video file")
        self.upload_button.clicked.connect(self.toggle_file_upload)

        self.youtube_button = self.create_button('./icons/youtube.svg', "Use Youtube Link")
        self.youtube_button.clicked.connect(self.toggle_youtube_container)

        self.record_button = self.create_button('./icons/record.svg', "Record from microphone/system audio")
        self.record_button.clicked.connect(self.toggle_voice_recorder)

        button_layout.addWidget(self.upload_button)
        button_layout.addWidget(self.youtube_button)
        button_layout.addWidget(self.record_button)

        main_layout.addLayout(button_layout)

        # Animations setup
        self.setup_animations()

    def on_update_progress(self, message):
        """Handle progress updates with visual feedback."""
        self.update_progress.emit(message)
        logging.info(message)

        # Update the progress label and ensure visibility
        self.progress_label.setText(message)
        self.progress_container.setVisible(True)

        # Reset progress display after a delay
        QTimer.singleShot(5000, self.reset_progress_display)

    def reset_progress_display(self):
        """Reset the progress display when operation completes."""
        self.progress_container.setVisible(False)

    def on_io_complete(self, filepath):
        """Handle completed file operations."""
        if not filepath or not os.path.exists(filepath):
            QMessageBox.warning(self, "File Error", "The processed file was not found.")
            return

        self.progress_container.setVisible(True)
        self.progress_label.setText(f"Processing: {os.path.basename(filepath)}")

        if filepath.endswith('.mp3'):
            self.progress_label.setText(f"Ready: {os.path.basename(filepath)}")
            QTimer.singleShot(2000, self.reset_progress_display)
            self.uploaded_filepath.emit(filepath)
        else:
            try:
                self.progress_label.setText(f"Transcoding: {os.path.basename(filepath)}")
                self.transcoding_thread = TranscodingThread(file_path=filepath)
                self.transcoding_thread.update_progress.connect(self.on_update_progress)
                self.transcoding_thread.completed.connect(self.on_transcoding_complete)
                self.transcoding_thread.error.connect(self.on_error)
                self.transcoding_thread.start()
            except Exception as e:
                self.on_error(f"Failed to start transcoding: {str(e)}")
                logging.error(f"Transcoding error: {e}", exc_info=True)

    def on_transcoding_complete(self, filepath):
        """Handle completion of transcoding operation."""
        logging.info(f"Transcoding completed. File saved to: {filepath}")
        self.progress_label.setText(f"Ready: {os.path.basename(filepath)}")
        QTimer.singleShot(2000, self.reset_progress_display)
        self.uploaded_filepath.emit(filepath)

    def on_error(self, message):
        """Handle error messages with visual feedback."""
        logging.error(f"Error: {message}")

        self.progress_label.setText(f"Error: {message}")
        self.progress_bar.setStyleSheet("QProgressBar { background-color: #ffeeee; }")
        QTimer.singleShot(5000, self.reset_progress_display)

        QMessageBox.critical(self, "Operation Failed", message)

    def setup_animations(self):
        """Setup animations for UI transitions."""
        # YouTube container animations
        self.youtube_container_animation = QPropertyAnimation(self.youtube_container, b"maximumHeight")
        self.youtube_container_animation.setDuration(300)  # Reduced from 500ms for snappier UI
        self.youtube_container_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)  # Fixed enum

        # Voice recorder widget animations
        self.voice_recorder_animation = QPropertyAnimation(self.voice_recorder_widget, b"maximumHeight")
        self.voice_recorder_animation.setDuration(300)
        self.voice_recorder_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)  # Fixed enum

        # File upload widget animations
        self.file_upload_animation = QPropertyAnimation(self.file_upload_widget, b"maximumHeight")
        self.file_upload_animation.setDuration(300)
        self.file_upload_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)  # Fixed enum

    def toggle_youtube_container(self):
        """Toggle YouTube URL input container visibility."""
        if self.active_widget == self.youtube_container:
            self.hide_all_widgets()
            return

        self.hide_all_widgets()
        self.toggle_container(self.youtube_container, self.youtube_container_animation)
        self.active_widget = self.youtube_container
        self.youtube_url_field.setFocus()  # Set focus to URL field for immediate input

    def toggle_voice_recorder(self):
        """Toggle voice recorder widget visibility."""
        if self.active_widget == self.voice_recorder_widget:
            self.hide_all_widgets()
            return

        self.hide_all_widgets()
        self.toggle_container(self.voice_recorder_widget, self.voice_recorder_animation)
        self.active_widget = self.voice_recorder_widget

    def toggle_file_upload(self):
        """Toggle file upload widget visibility."""
        if self.active_widget == self.file_upload_widget:
            self.hide_all_widgets()
            return

        self.hide_all_widgets()
        self.toggle_container(self.file_upload_widget, self.file_upload_animation)
        self.active_widget = self.file_upload_widget

    def hide_all_widgets(self):
        """Hide all input widgets."""
        for widget, animation in [
            (self.youtube_container, self.youtube_container_animation),
            (self.voice_recorder_widget, self.voice_recorder_animation),
            (self.file_upload_widget, self.file_upload_animation)
        ]:
            if widget.isVisible():
                self.collapse_widget(widget, animation)

        self.active_widget = None

    def toggle_container(self, widget, animation):
        """Toggle container visibility with animation."""
        is_visible = widget.isVisible() and widget.maximumHeight() > 0
        current_height = widget.sizeHint().height() if is_visible else 0
        target_height = 0 if is_visible else widget.sizeHint().height()

        # Disconnect any existing 'finished' signal connections
        try:
            animation.finished.disconnect()
        except TypeError:
            # No connections to disconnect, safe to ignore
            pass

        # Connect 'finished' signal to handle visibility post-animation
        animation.finished.connect(lambda: self.handle_animation_finished(widget, target_height))

        widget.setVisible(True)  # Ensure the widget is visible for the animation
        animation.setStartValue(current_height)
        animation.setEndValue(target_height)
        animation.start()

    def collapse_widget(self, widget, animation):
        """Collapse a widget with animation."""
        try:
            animation.finished.disconnect()
        except TypeError:
            pass

        animation.finished.connect(lambda: widget.setVisible(False))
        animation.setStartValue(widget.height())
        animation.setEndValue(0)
        animation.start()

    def handle_animation_finished(self, widget, target_height):
        """Handle post-animation state of widgets."""
        # Hide the widget if the target height is 0
        if target_height == 0:
            widget.setVisible(False)

    def create_button(self, icon_path, tool_tip):
        """Create a styled button with icon."""
        # Use resource_path to get the absolute path
        absolute_icon_path = resource_path(icon_path)

        button = QPushButton()

        # Verify icon file exists
        if not os.path.exists(absolute_icon_path):
            logging.warning(f"Icon file not found: {absolute_icon_path}")
            # Create a button with text instead
            button.setText(tool_tip.split()[-1])  # Use last word of tooltip as button text
        else:
            button.setIcon(QIcon(absolute_icon_path))
            button.setIconSize(QSize(25, 25))

        button.setFixedSize(40, 40)
        button.setToolTip(tool_tip)
        button.setStyleSheet(self.button_stylesheet())
        return button

    def button_stylesheet(self):
        """Define stylesheet for buttons."""
        return """
            QPushButton {
                background-color: #f5f5f5;
                border-radius: 20px;
                border: 1px solid #dcdcdc;
            }

            QPushButton:hover {
                background-color: #e0e0e0;
                border: 1px solid #c0c0c0;
            }

            QPushButton:pressed {
                background-color: #d0d0d0;
                border: 1px solid #a0a0a0;
            }
        """

    def submit_youtube_url(self):
        """Process the YouTube URL submission."""
        youtube_url = self.youtube_url_field.text().strip()

        if not youtube_url:
            QMessageBox.warning(self, "Empty URL", "Please enter a YouTube URL.")
            return

        if validate_url(youtube_url):
            self.progress_container.setVisible(True)
            self.progress_label.setText(f"Downloading YouTube audio: {youtube_url}")

            # Hide the YouTube container
            self.toggle_youtube_container()

            # Clear the URL field for next use
            self.youtube_url_field.clear()

            try:
                self.youtube_download_thread = YouTubeDownloadThread(youtube_url=youtube_url)
                self.youtube_download_thread.update_progress.connect(self.on_update_progress)
                self.youtube_download_thread.completed.connect(self.on_io_complete)
                self.youtube_download_thread.error.connect(self.on_error)
                self.youtube_download_thread.start()
            except Exception as e:
                self.on_error(f"Failed to start YouTube download: {str(e)}")
                logging.error(f"YouTube download error: {e}", exc_info=True)
        else:
            QMessageBox.warning(self, "Invalid URL",
                                "Please enter a valid YouTube URL (e.g., https://www.youtube.com/watch?v=dQw4w9WgXcQ)")