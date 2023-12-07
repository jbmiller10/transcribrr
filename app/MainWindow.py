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

    def add_recording(self, full_file_path):
        recording_item_widget = RecordingListItem(full_file_path)

        item = QListWidgetItem(self.recordings_list)
        item.setSizeHint(recording_item_widget.sizeHint())

        self.recordings_list.addItem(item)
        self.recordings_list.setItemWidget(item, recording_item_widget)

        # Optionally store the metadata in the item's data
        item.setData(Qt.UserRole, recording_item_widget.metadata)

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

class RecordingListItem(QWidget):
    def __init__(self, full_file_path, *args, **kwargs):
        super(RecordingListItem, self).__init__(*args, **kwargs)

        # Extract the filename without the extension
        filename = os.path.basename(full_file_path)
        filename_no_ext = os.path.splitext(filename)[0]

        # Extract the creation date and duration from the file metadata
        creation_date = datetime.datetime.fromtimestamp(
            os.path.getmtime(full_file_path)
        ).strftime("%Y-%m-%d %H:%M:%S")
        audio = AudioSegment.from_file(full_file_path)
        duration = str(datetime.timedelta(milliseconds=len(audio))).split('.')[0]

        self.name_editable = QLineEdit(filename_no_ext)
        self.name_editable = EditableLineEdit(filename_no_ext)
        self.name_editable.editingFinished.connect(self.finishEditing)
        self.date_label = QLabel(creation_date)
        self.duration_label = QLabel(duration)

        self.name_editable.setStyleSheet(
            "QLineEdit { color: grey; font-size: 16px; border: none; background: transparent;font-family: Roboto; }")
        self.date_label.setStyleSheet("color: grey; font-size: 12px;")
        self.duration_label.setStyleSheet("color: grey; font-size: 12px;")

        layout = QHBoxLayout()
        v_layout = QVBoxLayout()
        v_layout.addWidget(self.name_editable)
        v_layout.addWidget(self.date_label)
        v_layout.addStretch()  # Pushes the labels to the top


        layout.addLayout(v_layout, 3)

        layout.addStretch(1)

        layout.addWidget(self.duration_label, 1)  # The second argument is the stretch factor

        self.setLayout(layout)

        # Align the duration label to the right
        self.duration_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # Store metadata for later use
        self.metadata = {
            'full_path': full_file_path,
            'filename': filename_no_ext,
            'date': creation_date,
            'duration': duration
        }

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.name_editable.setReadOnly(False)  # Allow editing
            self.name_editable.setFocus(Qt.MouseFocusReason)

    def finishEditing(self):
        new_name = self.name_editable.text()

class EditableLineEdit(QLineEdit):
    def __init__(self, *args, **kwargs):
        super(EditableLineEdit, self).__init__(*args, **kwargs)
        self.setReadOnly(True)  # Start as read-only

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setReadOnly(False)  # Allow editing
            self.selectAll()  # Optionally select all text to make editing easier
            QLineEdit.mouseDoubleClickEvent(self, event)  # Pass the event to the base class

    def focusOutEvent(self, event):
        self.setReadOnly(True)  # Make read-only again when focus is lost
        QLineEdit.focusOutEvent(self, event)  # Pass the event to the base class

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

        # Load existing recordings
        self.recent_recordings_widget.load_recordings()

        # Connect the signals to their respective slots
        self.recent_recordings_widget.recordingSelected.connect(self.on_recording_selected)
        self.main_transcription_widget.transcriptionStarted.connect(self.on_transcription_started)
        self.main_transcription_widget.transcriptionStopped.connect(self.on_transcription_stopped)
        self.main_transcription_widget.transcriptionSaved.connect(self.on_transcription_saved)
        self.main_transcription_widget.settingsRequested.connect(self.on_settings_requested)
        self.voice_recorder_widget.recordingCompleted.connect(self.onRecordingCompleted)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)



    def on_recording_selected(self, filename):
        # TODO: Implement what happens when a recording is selected
        pass

    def onRecordingCompleted(self, file_name):
        # Add the new recording to the RecentRecordingsWidget
        self.recent_recordings_widget.add_recording(file_name)
        # Optionally, you could select the new recording in the list
        self.recent_recordings_widget.recordings_list.setCurrentRow(
            self.recent_recordings_widget.recordings_list.count() - 1
        )
        # Display a notification
        QMessageBox.information(self, "Recording Completed", f"Recording saved: {file_name}")


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