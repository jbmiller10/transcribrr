from PyQt6.QtCore import pyqtSignal, QSize, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QFileDialog, QMessageBox, QLineEdit, QApplication, QMainWindow, QVBoxLayout, QLabel
import os
import shutil
import sys
from app.utils import is_video_file, is_audio_file, validate_url
from app.TranscodingThread import TranscodingThread
from app.YouTubeDownloadThread import YouTubeDownloadThread
from app.VoiceRecorderWidget import VoiceRecorderWidget
from app.FileDropWidget import FileDropWidget


class ControlPanelWidget(QWidget):
    uploaded_filepath = pyqtSignal(str)
    record_clicked = pyqtSignal()
    youtube_download_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        main_layout = QVBoxLayout(self)

        # YouTube container setup
        self.youtube_container = QWidget(self)
        youtube_layout = QHBoxLayout(self.youtube_container)
        self.youtube_url_field = QLineEdit(self.youtube_container)
        self.youtube_url_field.setPlaceholderText("Enter YouTube URL here")
        youtube_layout.addWidget(self.youtube_url_field)
        self.submit_youtube_url_button = QPushButton("Submit", self.youtube_container)
        self.submit_youtube_url_button.clicked.connect(self.submit_youtube_url)
        youtube_layout.addWidget(self.submit_youtube_url_button)
        main_layout.addWidget(self.youtube_container)
        self.youtube_container.setVisible(False)

        # Voice recorder widget setup
        self.voice_recorder_widget = VoiceRecorderWidget(self)
        main_layout.addWidget(self.voice_recorder_widget)
        self.voice_recorder_widget.recordingCompleted.connect(self.uploaded_filepath.emit)
        self.voice_recorder_widget.setVisible(False)

        # Voice recorder widget setup
        main_layout.addWidget(self.voice_recorder_widget)
        self.voice_recorder_widget.recordingCompleted.connect(self.uploaded_filepath.emit)
        self.voice_recorder_widget.setVisible(False)

        #File Drop Widget setup
        self.file_upload_widget = FileDropWidget(self)  # Adjust as per your actual widget
        main_layout.addWidget(self.file_upload_widget)
        self.file_upload_widget.setVisible(False)
        #self.voice_recorder_widget.recordingCompleted.connect(self.uploaded_filepath.emit)


        # Button layout setup
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



    def setup_animations(self):
        # YouTube container animations
        self.youtube_container_animation = QPropertyAnimation(self.youtube_container, b"maximumHeight")
        self.youtube_container_animation.setDuration(500)
        self.youtube_container_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)

        # Voice recorder widget animations
        self.voice_recorder_animation = QPropertyAnimation(self.voice_recorder_widget, b"maximumHeight")
        self.voice_recorder_animation.setDuration(500)
        self.voice_recorder_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)

        # file upload widget animations
        self.file_upload_animation = QPropertyAnimation(self.file_upload_widget, b"maximumHeight")
        self.file_upload_animation.setDuration(500)
        self.file_upload_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)

    def toggle_youtube_container(self):
        # If voice recorder widget is visible, toggle it off
        if self.voice_recorder_widget.isVisible():
            self.toggle_voice_recorder()
        elif self.file_upload_widget.isVisible():
            self.toggle_file_upload()

        self.toggle_container(self.youtube_container, self.youtube_container_animation)

    def toggle_voice_recorder(self):
        # If YouTube container is visible, toggle it off
        if self.youtube_container.isVisible():
            self.toggle_youtube_container()
        elif self.file_upload_widget.isVisible():
            self.toggle_file_upload()

        self.toggle_container(self.voice_recorder_widget, self.voice_recorder_animation)

    def toggle_file_upload(self):
        # Hide other containers if visible
        if self.youtube_container.isVisible():
            self.toggle_youtube_container()
        elif self.voice_recorder_widget.isVisible():
            self.toggle_voice_recorder()

        # Toggle the file upload widget
        self.toggle_container(self.file_upload_widget, self.file_upload_animation)

    def toggle_container(self, widget, animation):
        is_visible = widget.isVisible()
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

    def handle_animation_finished(self, widget, target_height):
        # Hide the widget if the target height is 0
        if target_height == 0:
            widget.setVisible(False)

    def create_button(self, icon_path, tool_tip):
        absolute_icon_path = os.path.abspath(icon_path)
        button = QPushButton()
        button.setIcon(QIcon(absolute_icon_path))
        button.setIconSize(QSize(25, 25))
        button.setFixedSize(40, 40)
        button.setToolTip(tool_tip)
        button.setStyleSheet(self.button_stylesheet())
        return button

    def button_stylesheet(self):
        return """
            /*QPushButton {
                background-color: transparent;
            }
            QPushButton:pressed {
                background-color: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 2,
                    stop: 0 #dadbde, stop: 1 #f6f7fa
                );
            }
            QPushButton:hover {
                border: 2px solid blue;
                border-radius: 6px;
            }*/
        """

    def submit_youtube_url(self):
        youtube_url = self.youtube_url_field.text().strip()
        if validate_url(youtube_url):
            self.youtube_download_requested.emit(youtube_url)
            self.toggle_youtube_container()
        else:
            QMessageBox.warning(self, "Invalid URL", "Please enter a valid YouTube URL.")

    def on_upload_button_clicked(self):
        file_dialog = QFileDialog(self)
        file_dialog.setNameFilter("Audio/Video Files (*.mp3 *.wav *.m4a *.ogg *.mp4 *.mkv *.avi *.mov)")
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        if file_dialog.exec() == QFileDialog.DialogCode.Accepted:
            original_file_path = file_dialog.selectedFiles()[0]
            self.uploaded_filepath.emit(original_file_path)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Transcribrr Test")
        self.setGeometry(100, 100, 800, 600)

        self.control_panel = ControlPanelWidget(self)
        self.control_panel.uploaded_filepath.connect(self.on_uploaded_filepath)

        layout = QVBoxLayout()
        self.status_label = QLabel("Status: Waiting for actions")
        layout.addWidget(self.control_panel)
        layout.addWidget(self.status_label)

        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    def on_uploaded_filepath(self, filepath):
        self.status_label.setText(f"File uploaded: {filepath}")

    def on_record_clicked(self):
        self.status_label.setText("Record button clicked")

def main():
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
