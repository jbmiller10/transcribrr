import re
import traceback
import datetime
import shutil
from PyQt6.QtCore import (
    pyqtSignal, QSize, Qt, QPropertyAnimation, QEasingCurve, QFile,
)
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QPushButton, QMessageBox,
    QWidget, QHBoxLayout, QLabel, QListWidget, QSizePolicy,
    QPushButton, QSpacerItem, QFileDialog, QMenu, QListWidgetItem, QMainWindow,QComboBox,QTextEdit, QSplitter,QStatusBar
)

from app.TranscodingThread import TranscodingThread
from app.VoiceRecorderWidget import VoiceRecorderWidget  # Import specific classes
import os
from app.RecordingListItem import RecordingListItem
from app.MainTranscriptionWidget import  MainTranscriptionWidget
from app.ControlPanelWidget import ControlPanelWidget


class RecentRecordingsWidget(QWidget):
    recordingSelected = pyqtSignal(str)
    recordButtonPressed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.header_label = QLabel("Recent Recordings")
        self.header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.recordings_list = QListWidget()

        self.button_stylesheet = """
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

        self.layout.addWidget(self.header_label)
        self.layout.addWidget(self.recordings_list)

        self.recordings_list.itemClicked.connect(self.recording_clicked)

        # Right click context menu for delete
        self.recordings_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.recordings_list.customContextMenuRequested.connect(self.showRightClickMenu)

    def add_recording(self, full_file_path):
        recording_item_widget = RecordingListItem(full_file_path)

        item = QListWidgetItem(self.recordings_list)
        item.setSizeHint(recording_item_widget.sizeHint())

        self.recordings_list.addItem(item)
        self.recordings_list.setItemWidget(item, recording_item_widget)

        # Optionally store the metadata in the item's data
        item.setData(Qt.ItemDataRole.UserRole, recording_item_widget.metadata)

    def load_recordings(self):
        recordings_dir = "Recordings"
        if not os.path.exists(recordings_dir):
            print("Recordings directory not found.")
            return

        supported_formats = ['.mp3', '.wav', '.ogg', '.flac']
        file_list = []

        try:
            for filename in os.listdir(recordings_dir):
                file_extension = os.path.splitext(filename)[1]
                if file_extension.lower() in supported_formats:
                    file_path = os.path.join(recordings_dir, filename)
                    file_list.append(file_path)

            # Now file_list contains full paths of all recordings
            for file_path in file_list:
                self.add_recording(file_path)

        except Exception as e:
            print("An error occurred while loading recordings:", e)
            traceback.print_exc()

    def recording_clicked(self, item: QListWidgetItem):
        filename = item.text()
        self.recordingSelected.emit(filename)

    def set_style(self):
        self.setStyleSheet("""
            QLabel {
                font-size: 18px;
                color: white;
                padding: 10px 0px; /* Top and bottom padding */
            }
            QListWidget {
                background-color: #333;
                color: white;
            }
            QPushButton {
                border-radius: 25px; /* Half of the button size for a circular look */
                background-color: #444;
                color: white;
            }
        """)
    def showRightClickMenu(self, position):
        # Get the global position for showing the context menu
        global_pos = self.recordings_list.viewport().mapToGlobal(position)

        # Create the context menu
        menu = QMenu()
        delete_action = menu.addAction("Delete")

        # Show the context menu and get the selected action
        action = menu.exec(global_pos)

        # If delete is clicked, call the method to delete the item
        if action == delete_action:
            self.deleteRecording(position)

    def deleteRecording(self, position):
        # Get the item at the clicked position
        item = self.recordings_list.itemAt(position)
        if item is None:
            return  # No item at the position

        # Confirm deletion with the user
        reply = QMessageBox.question(self, 'Delete Recording',
                                     'Are you sure you want to delete this recording?',
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            # Proceed with deletion
            row = self.recordings_list.row(item)
            full_file_path = item.data(Qt.ItemDataRole.UserRole)['full_path']
            # Optionally, delete the file from the filesystem
            os.remove(full_file_path)
            self.recordings_list.takeItem(row)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        # Initialize the window properties
        self.setWindowTitle('Transcribrr')
        self.setGeometry(50, 50, 1350, 768)

        # Create instances of widgets
        self.control_panel = ControlPanelWidget(self)
        self.recent_recordings_widget = RecentRecordingsWidget()
        self.main_transcription_widget = MainTranscriptionWidget()

        # Connect signals

        # Set up the central widget and its layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)

        # Create a QSplitter to manage the layout of the left and right sections
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        self.main_layout.addWidget(self.splitter)

        # Layout for the left side section
        self.left_layout = QVBoxLayout()
        self.left_layout.addWidget(self.recent_recordings_widget,12)
        self.left_layout.addWidget(self.control_panel,0)

        self.recent_recordings_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.control_panel.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.MinimumExpanding)

        # Create a widget to hold the left_layout
        self.left_widget = QWidget()
        self.left_widget.setLayout(self.left_layout)

        # Add left_widget to the splitter and define its initial size
        self.splitter.addWidget(self.left_widget)
        self.splitter.setSizes([400, 950])

        # Load existing recordings, if any
        self.recent_recordings_widget.load_recordings()

        # Assuming you have a widget for managing transcriptions
        self.main_transcription_widget = MainTranscriptionWidget()

        # Add the left panel (recent recordings and controls) to the splitter
        self.splitter.addWidget(self.left_widget)

        # Additionally, add the main transcription area to the right side of the splitter
        self.splitter.addWidget(self.main_transcription_widget)

        self.control_panel.uploaded_filepath.connect(self.onRecordingCompleted)

        # Set the initial side ratios of the splitter (e.g., 1:2)
        self.splitter.setSizes([400, 800])

        # Set status bar for the window, initially hidden
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.setVisible(False)

        # Set the initial style for the window
        self.set_style()

    def set_style(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #252525;
                color: white;
            }
            QLabel {
                font-size: 18px;
                color: white;
                padding: 10px 0px; /* Top and bottom padding */
            }
            QListWidget {
                background-color: #333;
                color: white;
            }
            QPushButton {
                border-radius: 25px; /* Half of the button size for a circular look */
                background-color: #444;
                color: white;
            }
        """)

    def onRecordingCompleted(self, file_name):
        # Call add_recording on the instance of RecentRecordingsWidget
        self.recent_recordings_widget.add_recording(file_name)

    def on_recording_selected(self, filename):
        # TODO: Implement what happens when a recording is selected
        pass

    def on_transcription_started(self):
        # TODO: Implement what happens when transcription starts
        pass

    def on_transcription_stopped(self):
        # TODO: Stop any ongoing transcription
        pass

    def on_transcription_saved(self, content):
        # TODO: Implement the transcription save functionality
        pass

    def on_settings_requested(self):
        # TODO: Open the settings dialog
        pass

    def set_style(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #252525;
                color: white;
            }
        """)

    def on_recording_completed(self, file_name):
        # Add the new recording to the RecentRecordingsWidget
        self.recent_recordings_widget.add_recording(file_name)
        # Optionally, you could select the new recording in the list
        self.recent_recordings_widget.recordings_list.setCurrentRow(
            self.recent_recordings_widget.recordings_list.count() - 1
        )
        # Display a notification
        QMessageBox.information(self, "Recording Completed", f"Recording saved: {file_name}")

    def start_transcoding(self, file_path):
        self.transcoding_thread = TranscodingThread(file_path, target_format='mp3')
        self.transcoding_thread.completed.connect(self.add_recording)
        self.transcoding_thread.error.connect(self.handle_transcoding_error)
        self.transcoding_thread.start()

    def handle_transcoding_error(self, error_message):
        QMessageBox.critical(self, "Transcoding Error", error_message)
