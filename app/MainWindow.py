import datetime
from PyQt6.QtCore import (
    Qt,
)
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QWidget, QHBoxLayout,  QSizePolicy,
    QMainWindow, QSplitter,QStatusBar
)
import os
from app.MainTranscriptionWidget import  MainTranscriptionWidget
from app.ControlPanelWidget import ControlPanelWidget
from app.database import create_connection, create_db, create_recording
from moviepy.editor import VideoFileClip, AudioFileClip
from app.utils import resource_path
from app.RecentRecordingsWidget import RecentRecordingsWidget



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

        self.recent_recordings_widget.recordingSelected.connect(self.main_transcription_widget.on_recording_item_selected)

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
        db_path = resource_path("./database/database.sqlite")
        conn = create_connection(db_path)
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



