from PyQt6.QtCore import pyqtSignal, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QFileDialog, QMessageBox
import os
import shutil
from app.utils import is_video_file,is_audio_file,validate_url
from app.TranscodingThread import *
import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QLabel

print("Current working directory:", os.getcwd())
class ControlPanelWidget(QWidget):
    uploaded_filepath = pyqtSignal(str)
    record_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        layout = QHBoxLayout(self)

        # Setup buttons and connect their signals
        self.upload_button = self.create_button('../icons/upload.svg', "Upload Local Audio/Video file")
        self.upload_button.clicked.connect(self.on_upload_button_clicked)

        self.youtube_button = self.create_button('../icons/youtube.svg', "Use Youtube Link")
        self.youtube_button.clicked.connect(self.youtube_button_click)

        self.record_button = self.create_button('../icons/record.svg', "Record from microphone/system audio")
        self.record_button.clicked.connect(self.record_button_click)

        layout.addWidget(self.upload_button)
        layout.addWidget(self.youtube_button)
        layout.addWidget(self.record_button)

    def create_button(self, icon_path, tool_tip):
        # Relative path from the 'app' directory to the 'icons' directory
        # Convert to an absolute path to avoid any relative path issues
        absolute_icon_path = os.path.abspath(icon_path)
        print(f"Attempting to load icon from: {absolute_icon_path}")
        button = QPushButton()
        button.setIcon(QIcon(absolute_icon_path))
        button.setIconSize(QSize(25, 25))
        button.setFixedSize(40, 40)
        button.setToolTip(tool_tip)
        button.setStyleSheet(self.button_stylesheet())
        return button
    def button_stylesheet(self):
        return """
            QPushButton {
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
            }
        """

    def youtube_button_click(self):
        # Logic when the YouTube button is clicked
        self.youtube_clicked.emit()

    def record_button_click(self):
        # Logic when the record button is clicked
        self.record_clicked.emit()

    def on_upload_button_clicked(self):
        file_dialog = QFileDialog(self)
        file_dialog.setNameFilter("Audio/Video Files (*.mp3 *.wav *.m4a *.ogg *.mp4 *.mkv *.avi *.mov)")
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        if file_dialog.exec() == QFileDialog.DialogCode.Accepted:
            original_file_path = file_dialog.selectedFiles()[0]
            target_file_path = self.copy_to_recordings(original_file_path)

            if is_video_file(target_file_path):
                self.start_transcoding_thread(target_file_path)
            elif is_audio_file(target_file_path):
                self.uploaded_filepath.emit(target_file_path)
            else:
                QMessageBox.warning(self, "File Type", "The selected file is not a supported audio or video type.")

    def copy_to_recordings(self, file_path):
        recordings_dir = "Recordings"
        os.makedirs(recordings_dir, exist_ok=True)
        base_name = os.path.basename(file_path)
        name, ext = os.path.splitext(base_name)
        counter = 1

        target_file_path = os.path.join(recordings_dir, base_name)
        while os.path.exists(target_file_path):
            target_file_path = os.path.join(recordings_dir, f"{name}_{counter}{ext}")
            counter += 1

        shutil.copyfile(file_path, target_file_path)
        return target_file_path

    def start_transcoding_thread(self, file_path):
        self.transcoding_thread = TranscodingThread(file_path, target_format='mp3')
        self.transcoding_thread.completed.connect(self.uploaded_filepath.emit)
        self.transcoding_thread.error.connect(lambda error: QMessageBox.critical(self, "Transcoding Error", error))
        self.transcoding_thread.start()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Transcribrr Test")
        self.setGeometry(100, 100, 800, 600)

        # Create an instance of ControlPanelWidget
        self.control_panel = ControlPanelWidget(self)

        # Connect the signals to slots
        self.control_panel.uploaded_filepath.connect(self.on_uploaded_filepath)
        self.control_panel.record_clicked.connect(self.on_record_clicked)

        # Layout
        layout = QVBoxLayout()
        self.status_label = QLabel("Status: Waiting for actions")
        layout.addWidget(self.control_panel)
        layout.addWidget(self.status_label)

        # Central Widget
        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    def on_uploaded_filepath(self, filepath):
        print(f"File uploaded: {filepath}")  # Print to console
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
