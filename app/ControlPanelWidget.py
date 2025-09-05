from PyQt6.QtCore import pyqtSignal, QSize, QPropertyAnimation, QEasingCurve, QTimer, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
    QVBoxLayout,
    QLabel,
    QProgressBar,
)
import os
import logging

# Use managers and ui_utils
from app.path_utils import resource_path
from app.ui_utils.icon_utils import load_icon
from app.utils import validate_url, resource_path, ConfigManager
from app.ui_utils import show_error_message, FeedbackManager
from app.threads.TranscodingThread import TranscodingThread
from app.threads.YouTubeDownloadThread import YouTubeDownloadThread
from app.VoiceRecorderWidget import VoiceRecorderWidget
from app.FileDropWidget import FileDropWidget
from app.ThreadManager import ThreadManager

# Configure logging (use app name)
logger = logging.getLogger("transcribrr")


class ControlPanelWidget(QWidget):
    # Renamed signal for clarity
    file_ready_for_processing = pyqtSignal(
        str)  # Now only emits a single file path
    # Removed record_clicked signal as VoiceRecorderWidget handles its own logic
    status_update = pyqtSignal(str)  # Use a more generic progress signal name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.transcoding_thread = None
        self.youtube_download_thread = None
        self.active_widget = None
        self.config_manager = ConfigManager.instance()  # Get config manager
        self.feedback_manager = FeedbackManager(self)  # Feedback management
        self.initUI()

    def initUI(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(5, 5, 5, 5)  # Reduced margins slightly

        # Progress bar container (reusable)
        self.progress_container = QWidget()
        progress_layout = QVBoxLayout(self.progress_container)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        self.progress_label = QLabel("Processing...")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.setTextVisible(False)
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.progress_container)
        self.progress_container.setVisible(False)

        # Input Widgets (initially hidden)
        self.youtube_container = self._create_youtube_container()
        self.voice_recorder_widget = self._create_voice_recorder()
        self.file_upload_widget = self._create_file_upload_widget()

        main_layout.addWidget(self.youtube_container)
        main_layout.addWidget(self.voice_recorder_widget)
        main_layout.addWidget(self.file_upload_widget)

        # Control Buttons
        button_layout = QHBoxLayout()
        self.upload_button = self.create_button(
            "./icons/upload.svg", "Upload Local File"
        )
        self.youtube_button = self.create_button(
            "./icons/youtube.svg", "Process YouTube URL"
        )
        self.record_button = self.create_button(
            "./icons/record.svg", "Record Audio")
        button_layout.addWidget(self.upload_button)
        button_layout.addWidget(self.youtube_button)
        button_layout.addWidget(self.record_button)
        main_layout.addLayout(button_layout)

        # Connect button signals
        self.upload_button.clicked.connect(
            lambda: self.toggle_widget(self.file_upload_widget)
        )
        self.youtube_button.clicked.connect(
            lambda: self.toggle_widget(self.youtube_container)
        )
        self.record_button.clicked.connect(
            lambda: self.toggle_widget(self.voice_recorder_widget)
        )

        self.setup_animations()

    # --- Widget Creation Helpers ---
    def _create_youtube_container(self):
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        self.youtube_url_field = QLineEdit(container)
        self.youtube_url_field.setPlaceholderText("Enter YouTube URL...")
        self.youtube_url_field.returnPressed.connect(self.submit_youtube_url)
        self.submit_youtube_url_button = QPushButton("Submit")
        self.submit_youtube_url_button.clicked.connect(self.submit_youtube_url)
        layout.addWidget(self.youtube_url_field, 1)
        layout.addWidget(self.submit_youtube_url_button)
        container.setVisible(False)
        return container

    def _create_voice_recorder(self):
        recorder = VoiceRecorderWidget(self)
        recorder.recordingCompleted.connect(
            self.handle_io_complete
        )  # Use renamed handler
        recorder.recordingError.connect(self.on_error)  # Connect error signal
        recorder.setVisible(False)
        return recorder

    def _create_file_upload_widget(self):
        uploader = FileDropWidget(self)
        uploader.fileDropped.connect(
            self.handle_io_complete)  # Use renamed handler
        uploader.setVisible(False)
        # Wrap in a layout to control margins if needed, but FileDropWidget might handle it
        # wrapper = QWidget()
        # layout = QVBoxLayout(wrapper)
        # layout.setContentsMargins(0,0,0,0)
        # layout.addWidget(uploader)
        # wrapper.setVisible(False)
        # return wrapper
        return uploader  # Return directly for now

    # --- UI State and Animations ---
    def setup_animations(self):
        self.widget_animations = {}
        for widget in [
            self.youtube_container,
            self.voice_recorder_widget,
            self.file_upload_widget,
        ]:
            animation = QPropertyAnimation(widget, b"maximumHeight")
            animation.setDuration(300)
            animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
            self.widget_animations[widget] = animation

    def toggle_widget(self, widget_to_show):
        """Toggle widgets visibility."""
        if self.active_widget == widget_to_show:
            # Hide the currently active widget
            self._animate_widget(self.active_widget, False)
            self.active_widget = None
        else:
            # Hide the previously active widget (if any)
            if self.active_widget:
                self._animate_widget(self.active_widget, False)
            # Show the new widget
            self._animate_widget(widget_to_show, True)
            self.active_widget = widget_to_show
            # Set focus for relevant widgets
            if widget_to_show == self.youtube_container:
                QTimer.singleShot(0, lambda: self.youtube_url_field.setFocus())

    def _animate_widget(self, widget, show):
        """Animate widget visibility."""
        animation = self.widget_animations.get(widget)
        if not animation:
            return

        start_height = widget.height()
        target_height = widget.sizeHint().height() if show else 0

        # Ensure widget is technically visible before starting show animation
        if show and not widget.isVisible():
            widget.setVisible(True)
            widget.setMaximumHeight(0)  # Start collapsed
            start_height = 0

        # Disconnect previous finished signal
        try:
            animation.finished.disconnect()
        except TypeError:
            pass

        # Connect finished signal to set visibility correctly after animation
        if not show:
            animation.finished.connect(lambda w=widget: w.setVisible(False))
        else:
            # If showing, ensure max height is reset after animation
            animation.finished.connect(
                lambda w=widget: w.setMaximumHeight(16777215)
            )  # Reset max height

        animation.setStartValue(start_height)
        animation.setEndValue(target_height)
        animation.start()

    # --- Progress and Status Updates ---
    def show_progress(self, message):
        self.progress_label.setText(message)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.setValue(-1)  # For some styles
        self.progress_container.setVisible(True)
        self.status_update.emit(message)  # Also emit general status

    def hide_progress(self, final_message=None, duration=2000):
        """Hide progress."""
        if final_message:
            self.progress_label.setText(final_message)
            self.progress_bar.setRange(0, 100)  # Determinate complete
            self.progress_bar.setValue(100)
            QTimer.singleShot(
                duration, lambda: self.progress_container.setVisible(False)
            )
            self.status_update.emit(final_message)  # Emit final status
        else:
            self.progress_container.setVisible(False)

    # --- Button Creation ---

    def create_button(self, icon_path, tool_tip):
        absolute_icon_path = resource_path(icon_path)
        button = QPushButton()
        if os.path.exists(absolute_icon_path):
            button.setIcon(load_icon(absolute_icon_path, size=24))
            button.setIconSize(QSize(22, 22))  # Slightly larger icons
        else:
            logger.warning(f"Icon not found: {absolute_icon_path}")
            # Use first word as text fallback
            button.setText(tool_tip.split()[0])
        button.setFixedSize(40, 40)  # Slightly larger buttons
        button.setToolTip(tool_tip)
        button.setStyleSheet(self.button_stylesheet())
        return button

    def button_stylesheet(self):
        # Stylesheet might be better handled by ThemeManager, but keep here for now
        return """
            QPushButton {
                background-color: #f0f0f0; /* Lighter base */
                border-radius: 6px; /* More rounded */
                border: 1px solid #c8c8c8;
                padding: 5px; /* Add padding */
            }
            QPushButton:hover {
                background-color: #e0e0e0;
                border: 1px solid #b0b0b0;
            }
            QPushButton:pressed {
                background-color: #d0d0d0;
                border: 1px solid #a0a0a0;
            }
            QPushButton:focus { /* Add focus indicator */
                border: 1px solid #77aaff; /* Example focus color */
                outline: none; /* Remove default outline */
            }
        """

    # --- Action Handlers ---
    def submit_youtube_url(self):
        youtube_url = self.youtube_url_field.text().strip()
        if not youtube_url:
            show_error_message(self, "Empty URL",
                               "Please enter a YouTube URL.")
            return

        if not validate_url(youtube_url):
            show_error_message(self, "Invalid URL",
                               "Please enter a valid YouTube URL.")
            return

        logger.info(f"Submitting YouTube URL: {youtube_url}")

        # Create UI elements to disable
        ui_elements = self.get_youtube_ui_elements()

        # Hide input container
        self.toggle_widget(self.youtube_container)
        self.youtube_url_field.clear()

        # Setup feedback
        truncated_url = youtube_url[:40] + \
            ("..." if len(youtube_url) > 40 else "")
        self.feedback_manager.set_ui_busy(True, ui_elements)
        self.feedback_manager.show_status(
            f"Requesting YouTube audio: {truncated_url}")

        # Create progress dialog for download
        self.yt_progress_id = "youtube_download"
        self.feedback_manager.start_progress(
            self.yt_progress_id,
            "YouTube Download",
            f"Downloading audio from: {truncated_url}",
            maximum=100,  # Determinate progress
            cancelable=True,
            cancel_callback=lambda: self.cancel_youtube_download(),
        )

        try:
            # Stop previous thread if running
            if (
                self.youtube_download_thread
                and self.youtube_download_thread.isRunning()
            ):
                self.youtube_download_thread.cancel()
                self.youtube_download_thread.wait(1000)

            self.youtube_download_thread = YouTubeDownloadThread(
                youtube_url=youtube_url
            )
            self.youtube_download_thread.update_progress.connect(
                self.on_youtube_progress
            )
            self.youtube_download_thread.completed.connect(
                self.handle_io_complete)
            self.youtube_download_thread.error.connect(self.on_error)

            # Register thread with ThreadManager
            ThreadManager.instance().register_thread(self.youtube_download_thread)
            self.youtube_download_thread.start()
        except Exception as e:
            self.on_error(f"Failed to start YouTube download: {e}")

    def get_youtube_ui_elements(self):
        """Return UI elements to disable for YouTube."""
        elements = []
        if hasattr(self, "youtube_button"):
            elements.append(self.youtube_button)
        if hasattr(self, "upload_button"):
            elements.append(self.upload_button)
        if hasattr(self, "record_button"):
            elements.append(self.record_button)
        if hasattr(self, "youtube_url_field"):
            elements.append(self.youtube_url_field)
        if hasattr(self, "submit_youtube_url_button"):
            elements.append(self.submit_youtube_url_button)
        return elements

    def cancel_youtube_download(self):
        """Cancel YouTube download."""
        if self.youtube_download_thread and self.youtube_download_thread.isRunning():
            logger.info("User requested cancellation of YouTube download")
            self.youtube_download_thread.cancel()
            self.feedback_manager.show_status("Cancelling YouTube download...")

    def on_youtube_progress(self, message):
        """Update YouTube download progress."""
        # Update status
        self.status_update.emit(message)

        # Extract progress percentage if available
        if "Downloading:" in message and "%" in message:
            try:
                percent_str = message.split("Downloading:")[
                    1].split("%")[0].strip()
                percent = float(percent_str)

                if hasattr(self, "yt_progress_id"):
                    self.feedback_manager.update_progress(
                        self.yt_progress_id, int(percent), message
                    )
            except (ValueError, IndexError):
                pass

    def handle_io_complete(self, filepath):
        """Handle completed file operations."""
        if not filepath or not os.path.exists(filepath):
            self.on_error(f"Processed file not found or invalid: {filepath}")
            return

        logger.info(f"IO complete, file path: {filepath}")

        # Close YouTube progress if it exists
        if hasattr(self, "yt_progress_id"):
            self.feedback_manager.finish_progress(
                self.yt_progress_id,
                f"Download complete: {os.path.basename(filepath)}",
                auto_close=True,
                delay=2000,
            )

        # Check if transcoding is needed (e.g., not mp3/wav)
        _, ext = os.path.splitext(filepath)
        if ext.lower() not in [
            ".mp3",
            ".wav",
        ]:  # Define supported directly usable formats
            logger.info(f"Transcoding needed for {filepath}")
            # Quick UI-level check for mute video to provide instant feedback
            try:
                # Lazy import moviepy only when needed for video
                from moviepy.editor import VideoFileClip
                with VideoFileClip(filepath) as test_clip:
                    if test_clip.audio is None:
                        self.on_error(
                            "The selected video file contains no audio track."
                        )
                        return
            except ImportError:
                logger.warning("MoviePy not available - skipping audio track check")
                # Continue without checking - let transcoding thread handle it
            except Exception as e:
                self.on_error(f"Error analyzing video file: {e}")
                return
            # Setup feedback for transcoding
            ui_elements = self.get_transcoding_ui_elements()
            self.feedback_manager.set_ui_busy(True, ui_elements)
            self.feedback_manager.show_status(
                f"Transcoding file: {os.path.basename(filepath)}"
            )

            # Create progress dialog for transcoding
            self.transcoding_progress_id = "transcoding"
            self.feedback_manager.start_progress(
                self.transcoding_progress_id,
                "Audio Transcoding",
                f"Converting file: {os.path.basename(filepath)}",
                maximum=0,  # Indeterminate for now
                cancelable=True,
                cancel_callback=lambda: self.cancel_transcoding(),
            )

            try:
                # Stop previous thread if running
                if self.transcoding_thread and self.transcoding_thread.isRunning():
                    # No explicit cancel in original, add if needed
                    self.transcoding_thread.wait(1000)

                # Chunking removed from this version

                self.transcoding_thread = TranscodingThread(file_path=filepath)
                self.transcoding_thread.update_progress.connect(
                    self.on_transcoding_progress
                )
                self.transcoding_thread.completed.connect(
                    self.on_transcoding_complete)
                self.transcoding_thread.error.connect(self.on_error)

                # Register thread with ThreadManager
                ThreadManager.instance().register_thread(self.transcoding_thread)
                self.transcoding_thread.start()
            except Exception as e:
                self.on_error(f"Failed to start transcoding: {e}")
        else:
            # File is already in a usable format
            logger.info(f"File {filepath} is ready, no transcoding needed.")

            # Finish any progress indicators
            if hasattr(self, "yt_progress_id"):
                self.feedback_manager.close_progress(self.yt_progress_id)

            # Show status and emit file ready signal
            self.feedback_manager.show_status(
                f"Ready: {os.path.basename(filepath)}")
            self.file_ready_for_processing.emit(filepath)

    def get_transcoding_ui_elements(self):
        """Return UI elements to disable for transcoding."""
        elements = []
        if hasattr(self, "youtube_button"):
            elements.append(self.youtube_button)
        if hasattr(self, "upload_button"):
            elements.append(self.upload_button)
        if hasattr(self, "record_button"):
            elements.append(self.record_button)
        return elements

    def cancel_transcoding(self):
        """Cancel transcoding."""
        if self.transcoding_thread and self.transcoding_thread.isRunning():
            logger.info("User requested cancellation of transcoding")
            self.transcoding_thread.cancel()  # Call the thread's cancel method
            self.feedback_manager.show_status("Cancelling transcoding...")

    def on_transcoding_progress(self, message):
        """Update transcoding progress."""
        # Update status
        self.status_update.emit(message)

        # Update progress dialog
        if hasattr(self, "transcoding_progress_id"):
            progress_value = 0  # Default indeterminate

            # Try to parse progress information
            if "Exporting chunk" in message and "/" in message:
                try:
                    parts = message.split()
                    for part in parts:
                        if "/" in part:
                            current, total = map(
                                int, part.strip(".,").split("/"))
                            progress_value = int(current * 100 / total)
                            break
                except (ValueError, IndexError):
                    pass

            self.feedback_manager.update_progress(
                self.transcoding_progress_id, progress_value, message
            )

    def on_transcoding_complete(self, file_path):
        """Handle transcoding completion."""
        try:
            # Finish progress dialog
            if hasattr(self, "transcoding_progress_id"):
                self.feedback_manager.close_progress(
                    self.transcoding_progress_id)
                delattr(self, "transcoding_progress_id")

            # Single file produced
            logger.info(f"Transcoding completed. File saved to: {file_path}")

            # Show status and emit file ready
            self.feedback_manager.show_status(
                f"Ready: {os.path.basename(file_path)}")

            self.file_ready_for_processing.emit(file_path)
        except Exception as e:
            logger.error(f"Error in transcoding completion handler: {e}")
            self.on_error(f"Failed to complete transcoding: {e}")

    def on_error(self, message):
        """Handle thread errors."""
        logger.error(f"Operation Error: {message}")

        # Clean up any active feedback
        if hasattr(self, "yt_progress_id"):
            self.feedback_manager.close_progress(self.yt_progress_id)
            delattr(self, "yt_progress_id")

        if hasattr(self, "transcoding_progress_id"):
            self.feedback_manager.close_progress(self.transcoding_progress_id)
            delattr(self, "transcoding_progress_id")

        # Show error message
        show_error_message(self, "Operation Failed", message)
        self.status_update.emit(f"Error: {message}")
