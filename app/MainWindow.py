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
import os
from app.RecordingListItem import RecordingListItem
from app.MainTranscriptionWidget import  MainTranscriptionWidget
from app.ControlPanelWidget import ControlPanelWidget
from app.database import create_connection, get_all_recordings, create_db, create_recording, update_recording, delete_recording
from moviepy.editor import VideoFileClip, AudioFileClip
from pydub import AudioSegment

class RecentRecordingsWidget(QWidget):
    recordingSelected = pyqtSignal(str)
    recordButtonPressed = pyqtSignal()
    recordingItemSelected = pyqtSignal(RecordingListItem)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.header_label = QLabel("Recent Recordings")
        self.header_label.setObjectName("RecentRecordingHeader")
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
        try:
            # Extract metadata from the file path
            filename = os.path.basename(full_file_path)
            date_created = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            audio = AudioSegment.from_file(full_file_path)
            duration = str(datetime.timedelta(milliseconds=len(audio))).split('.')[0]

            # Create a new recording in the database
            conn = create_connection("./database/database.sqlite")
            recording_data = (filename, full_file_path, date_created, duration, "", "")
            recording_id = create_recording(conn, recording_data)

            # Now create the RecordingListItem with the new database id
            recording_item_widget = RecordingListItem(recording_id, full_file_path)
            recording_item_widget.metadata = {
                'id': recording_id,
                'full_path': full_file_path,
                'filename': filename,
                'date': date_created,
                'duration': duration
            }

            # Create the QListWidgetItem and set its size hint
            item = QListWidgetItem(self.recordings_list)
            item.setSizeHint(recording_item_widget.sizeHint())

            # Add the QListWidgetItem to the list and set the custom widget
            self.recordings_list.addItem(item)
            self.recordings_list.setItemWidget(item, recording_item_widget)

            # Set the metadata for the QListWidgetItem
            item.setData(Qt.ItemDataRole.UserRole, recording_item_widget.metadata)

        except Exception as e:
            print(f"An error occurred: {e}")
            traceback.print_exc()
    # def load_recordings(self):
    #     recordings_dir = "Recordings"
    #     if not os.path.exists(recordings_dir):
    #         print("Recordings directory not found.")
    #         return
    #
    #     supported_formats = ['.mp3', '.wav', '.ogg', '.flac']
    #     file_list = []
    #
    #     try:
    #         for filename in os.listdir(recordings_dir):
    #             file_extension = os.path.splitext(filename)[1]
    #             if file_extension.lower() in supported_formats:
    #                 file_path = os.path.join(recordings_dir, filename)
    #                 file_list.append(file_path)
    #
    #         # Now file_list contains full paths of all recordings
    #         for file_path in file_list:
    #             self.add_recording(file_path)
    #
    #     except Exception as e:
    #         print("An error occurred while loading recordings:", e)
    #         traceback.print_exc()

    def recording_clicked(self, item: QListWidgetItem):
        recording_item_widget = self.recordings_list.itemWidget(item)
        self.recordingItemSelected.emit(recording_item_widget)

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
            self.delete_selected_recording()


    def update_status_bar(self, message):
        self.status_bar.showMessage(message)

    def delete_selected_recording(self):
        current_item = self.recordings_list.currentItem()
        if current_item is not None:
            response = QMessageBox.question(self, 'Delete Recording',
                                            'Are you sure you want to delete this recording?',
                                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if response == QMessageBox.StandardButton.Yes:
                recording_id = current_item.data(Qt.ItemDataRole.UserRole)['id']
                self.delete_recording_from_db(recording_id)
                row = self.recordings_list.row(current_item)
                self.recordings_list.takeItem(row)

    def delete_recording_from_db(self, recording_id):
        conn = create_connection("./database/database.sqlite")
        delete_recording(conn, recording_id)

    def load_recordings(self):
        """Load recordings from the database and populate the list."""
        conn = create_connection("./database/database.sqlite")
        recordings = get_all_recordings(conn)
        for recording in recordings:
            id, filename, file_path, date_created, duration, raw_transcript, processed_text = recording
            self.add_recording_to_list(id, filename, file_path, date_created, duration, raw_transcript, processed_text)

    def add_recording_to_list(self, id, filename, file_path, date_created, duration, raw_transcript, processed_text):
        recording_item_widget = RecordingListItem(id, filename, file_path, date_created, duration, raw_transcript, processed_text)  # Initialize your widget here
        #recording_item_widget.set_raw_transcript(raw_transcript)
        #recording_item_widget.set_processed_text(processed_text)

        # Set metadata
        recording_item_widget.metadata = {
            'id': id,
            'filename': filename,
            'full_path': file_path,
            'date_created': date_created,
            'duration': duration
        }

        # Add item to the list
        item = QListWidgetItem(self.recordings_list)
        item.setSizeHint(recording_item_widget.sizeHint())

        # Here is the crucial step: set the metadata on the QListWidgetItem
        item.setData(Qt.ItemDataRole.UserRole, recording_item_widget.metadata)

        self.recordings_list.addItem(item)
        self.recordings_list.setItemWidget(item, recording_item_widget)

    def save_recordings(self):
        """Save all recordings from the list to the database."""
        conn = create_connection("./database/database.sqlite")
        for index in range(self.recordings_list.count()):
            item = self.recordings_list.item(index)
            recording_item_widget = self.recordings_list.itemWidget(item)
            recording = (
                recording_item_widget.get_raw_transcript(),
                recording_item_widget.get_processed_text(),
                recording_item_widget.metadata['id']
            )
            update_recording(conn, recording)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()


    def init_ui(self):
        # Initialize the window properties
        self.setWindowTitle('Transcribrr')
        self.setGeometry(50, 50, 1350, 768)

        #create db if needed
        create_db()

        # Create instances of widgets
        self.control_panel = ControlPanelWidget(self)
        self.recent_recordings_widget = RecentRecordingsWidget()
        self.main_transcription_widget = MainTranscriptionWidget()
        #self.control_panel.update_progress.connect(self.update_status_bar)

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

        self.control_panel.uploaded_filepath.connect(self.on_new_file)

        # Set the initial side ratios of the splitter (e.g., 1:2)
        self.splitter.setSizes([400, 800])

        self.status_bar = QStatusBar()
        #self.statusBar().setStyleSheet("QStatusBar{color: red;}")
        self.setStatusBar(self.status_bar)
        self.status_bar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        fixed_height = 10
        self.status_bar.setFixedHeight(fixed_height)
        self.status_bar.setVisible(True)
        self.status_bar.showMessage("This is a status message.")

        self.recent_recordings_widget.recordingSelected.connect(self.main_transcription_widget.set_file_path)

        self.recent_recordings_widget.recordingItemSelected.connect(self.main_transcription_widget.on_recording_item_selected)

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

    def on_new_file(self, file_path):
        # Extract metadata from the file path
        filename = os.path.basename(file_path)
        date_created = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Assume you have a method to calculate the duration of the recording
        duration = self.calculate_duration(file_path)

        # Create a new recording in the database
        conn = create_connection("./database/database.sqlite")
        recording_data = (filename, file_path, date_created, duration, "", "")
        recording_id = create_recording(conn, recording_data)

        # Add the recording to the recent recordings widget
        self.recent_recordings_widget.add_recording_to_list(recording_id, filename, file_path, date_created, duration,
                                                            "", "")

    def calculate_duration(self, file_path):
        # Determine if the file is audio or video to use the appropriate MoviePy class
        if file_path.lower().endswith(('.mp3', '.wav', '.aac', '.flac', '.ogg', '.m4a')):
            clip = AudioFileClip(file_path)
        else:
            clip = VideoFileClip(file_path)

        # Calculate the duration
        duration_in_seconds = clip.duration
        clip.close()  # Close the clip to release the file

        # Format the duration as HH:MM:SS
        duration_str = str(datetime.timedelta(seconds=int(duration_in_seconds)))
        return duration_str
    def update_status_bar(self, message):
        self.statusBar().showMessage(message)
        print('whee'+message)
    def set_style(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #252525;
                color: black;
            }
            statusBar {
    background-color: #252525;
                color: red;
            }
        """)



