import re
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import os
import traceback
#from PyQt5.QtWidgets import  QLabel, QLineEdit
import keyring
import json
from app.YouTubeDownloadThread import YouTubeDownloadThread
from app.SettingsDialog import SettingsDialog
from app.TranscodingThread import TranscodingThread
from app.TranscriptionThread import TranscriptionThread
from app.GPT4ProcessingThread import GPT4ProcessingThread
from app.VoiceRecorderWidget import *


class RecentRecordingsWidget(QWidget):
    recordingSelected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.header_label = QLabel("Recent Recordings")
        self.header_label.setAlignment(Qt.AlignCenter)

        self.recordings_list = QListWidget()
        self.add_button = QPushButton()
        self.add_button.setIcon(QIcon('icons/add.svg'))  # path to '+' icon
        self.add_button.setFixedSize(50, 50)

        self.layout.addWidget(self.header_label)
        self.layout.addWidget(self.recordings_list)
        self.layout.addWidget(self.add_button, 0, Qt.AlignCenter)

        self.add_button.clicked.connect(self.add_recording)
        self.recordings_list.itemClicked.connect(self.recording_clicked)

    def add_recording(self):
        # TODO: Implement logic to add a recording
        pass

    def recording_clicked(self, item: QListWidgetItem):
        filename = item.text()
        self.recordingSelected.emit(filename)

    def populate_recordings(self, recordings):
        self.recordings_list.clear()
        for recording in recordings:
            item = QListWidgetItem(recording['filename'])
            item.setData(Qt.UserRole, recording)  # Store the entire recording info in the item
            self.recordings_list.addItem(item)

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


class MainTranscriptionWidget(QWidget):
    transcriptionStarted = pyqtSignal()
    transcriptionStopped = pyqtSignal()
    transcriptionSaved = pyqtSignal(str)
    settingsRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.transcription_type_combo = QComboBox()
        self.transcription_type_combo.addItems([
            'Journal Entry', 'Meeting Minutes', 'Interview Summary'
        ])

        self.play_button = QPushButton()
        self.play_button.setIcon(QIcon('icons/play.svg'))  # path to 'play' icon
        self.play_button.setFixedSize(50, 50)  # Adjust size as needed

        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon('icons/save.svg'))  # path to 'save' icon
        self.save_button.setFixedSize(50, 50)  # Adjust size as needed

        self.settings_button = QPushButton()
        self.settings_button.setIcon(QIcon('icons/settings.svg'))  # path to 'settings' icon
        self.settings_button.setFixedSize(50, 50)  # Adjust size as needed

        self.transcript_text = QTextEdit()

        self.layout.addWidget(self.transcription_type_combo)
        self.layout.addWidget(self.play_button)
        self.layout.addWidget(self.save_button)
        self.layout.addWidget(self.settings_button)
        self.layout.addWidget(self.transcript_text)

        self.play_button.clicked.connect(self.toggle_transcription)
        self.save_button.clicked.connect(self.save_transcription)
        self.settings_button.clicked.connect(self.request_settings)

    def toggle_transcription(self):
        if self.play_button.text() == 'Play':
            self.play_button.setIcon(QIcon('icons/stop.svg'))  # path to 'stop' icon
            self.transcriptionStarted.emit()
            self.play_button.setText('Stop')
        else:
            self.play_button.setIcon(QIcon('icons/play.svg'))  # path to 'play' icon
            self.transcriptionStopped.emit()
            self.play_button.setText('Play')

    def save_transcription(self):
        content = self.transcript_text.toPlainText()
        self.transcriptionSaved.emit(content)

    def request_settings(self):
        self.settingsRequested.emit()

    def set_style(self):
        self.setStyleSheet("""
            QPushButton {
                border-radius: 25px; /* Half of the button size for a circular look */
                background-color: #444;
                color: white;
            }
            QTextEdit {
                background-color: #333;
                color: white;
            }
        """)


# ... [rest of your imports]
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Transcribrr')
        self.setGeometry(100, 100, 1350, 768)

        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)

        # Use QVBoxLayout for stacking widgets vertically
        self.left_layout = QVBoxLayout()

        self.recent_recordings_widget = RecentRecordingsWidget()
        self.voice_recorder_widget = VoiceRecorderWidget()  # The voice recorder widget
        self.main_transcription_widget = MainTranscriptionWidget()

        # Add the RecentRecordingsWidget and VoiceRecorderWidget to left_layout
        self.left_layout.addWidget(self.recent_recordings_widget)
        self.left_layout.addWidget(self.voice_recorder_widget)

        # Create a QWidget to hold the left side layout
        self.left_widget = QWidget()
        self.left_widget.setLayout(self.left_layout)

        # QSplitter to split left and right sections
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.left_widget)
        splitter.addWidget(self.main_transcription_widget)
        splitter.setSizes([400, 950])

        # Main layout for the central widget, add the splitter to it
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.addWidget(splitter)

        # Connect the signals to their respective slots
        self.recent_recordings_widget.recordingSelected.connect(self.on_recording_selected)
        self.main_transcription_widget.transcriptionStarted.connect(self.on_transcription_started)
        self.main_transcription_widget.transcriptionStopped.connect(self.on_transcription_stopped)
        self.main_transcription_widget.transcriptionSaved.connect(self.on_transcription_saved)
        self.main_transcription_widget.settingsRequested.connect(self.on_settings_requested)
        self.voice_recorder_widget.recordingCompleted.connect(self.onRecordingCompleted)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Sample data to populate the recordings list
        sample_recordings = [
            {'filename': 'File_1.wav', 'date': '2022-12-06', 'duration': '00:02:33'},
            # ... add other recording data
        ]
        self.recent_recordings_widget.populate_recordings(sample_recordings)

    def on_recording_selected(self, filename):
        # TODO: Implement what happens when a recording is selected
        pass
    def onRecordingCompleted(self, file_name):
        # Logic to add the new recording to 'RecentRecordingsWidget' or perform any other action
        print(f"New recording completed: {file_name}")

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