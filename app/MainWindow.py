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
import datetime
import shutil


class YouTubeDownloadDialog(QDialog):
    download_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.url_input = QLineEdit(self)
        self.layout.addWidget(self.url_input)

        self.download_button = QPushButton("Download", self)
        self.download_button.clicked.connect(self.on_download_clicked)
        self.layout.addWidget(self.download_button)

    def on_download_clicked(self):
        url = self.url_input.text()
        if self.validate_url(url):
            self.download_requested.emit(url)
            self.accept()
        else:
            QMessageBox.warning(self, "Invalid URL", "The provided URL is not a valid YouTube URL.")

    @staticmethod
    def validate_url(url):
        # Use regex to validate the URL
        regex = r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
        return re.match(regex, url) is not None

class RecentRecordingsWidget(QWidget):
    recordingSelected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.header_label = QLabel("Recent Recordings")
        self.header_label.setAlignment(Qt.AlignCenter)

        self.recordings_list = QListWidget()


        self.buttonLayout = QHBoxLayout()
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

        #self.download_youtube_button = QPushButton("Download YouTube Video")
        self.add_button = QPushButton()
        self.add_button.setIcon(QIcon('icons/upload.svg'))
        self.add_button.setIconSize(QSize(40, 40))
        self.add_button.setFixedSize(40,40)
        self.add_button.setToolTip("Upload Local Audio/Video file")
        self.add_button.setStyleSheet(self.button_stylesheet)

        self.download_youtube_button = QPushButton()
        self.download_youtube_button.setIcon(QIcon('icons/youtube.svg'))
        self.download_youtube_button.setIconSize(QSize(40, 40))
        self.download_youtube_button.setFixedSize(40, 40)
        self.download_youtube_button.setToolTip("Use Youtube Link")
        self.download_youtube_button.setStyleSheet(self.button_stylesheet)

        self.record_new_button = QPushButton()
        self.record_new_button.setIcon(QIcon('icons/record.svg'))
        self.record_new_button.setIconSize(QSize(40, 40))
        self.record_new_button.setFixedSize(40, 40)
        self.record_new_button.setToolTip("Record from microphone/system audio")
        self.record_new_button.setStyleSheet(self.button_stylesheet)


        #self.buttonLayout.addWidget(self.add_button)x
        ##add to buttonlayout
        self.buttonLayout.addWidget(self.add_button)
        self.buttonLayout.addWidget(self.download_youtube_button)
        self.buttonLayout.addWidget(self.record_new_button)
        buttonSpacer = QSpacerItem(50,50, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.buttonLayout.addItem(buttonSpacer)
        #self.recordings_list.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        self.layout.addWidget(self.header_label)
        self.layout.addWidget(self.recordings_list)
        #self.layout.addStretch(1)
        self.layout.addLayout(self.buttonLayout)

        self.recordings_list.itemClicked.connect(self.recording_clicked)
        self.download_youtube_button.clicked.connect(self.on_download_youtube_clicked)
        self.add_button.clicked.connect(self.on_add_button_clicked)

        # Right click context menu for delete
        self.recordings_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.recordings_list.customContextMenuRequested.connect(self.showRightClickMenu)


    def on_add_button_clicked(self):
        file_dialog = QFileDialog(self)
        file_dialog.setNameFilter("Audio/Video Files (*.mp3 *.wav *.m4a *.ogg *.mp4 *.mkv *.avi *.mov)")
        file_dialog.setFileMode(QFileDialog.ExistingFile)
        if file_dialog.exec_() == QFileDialog.Accepted:
            selected_file_path = file_dialog.selectedFiles()[0]
            self.handle_file_addition(selected_file_path)


    def handle_file_addition(self, file_path):
        if self.is_video_file(file_path):
            # If it's a video file, extract the audio and transcode to MP3
            self.transcoding_thread = TranscodingThread(file_path, target_format='mp3')
            self.transcoding_thread.completed.connect(self.add_recording)
            self.transcoding_thread.error.connect(self.handle_transcoding_error)
            self.transcoding_thread.start()
        elif self.is_audio_file(file_path):
            # If it's an audio file, copy it to the recordings directory
            target_file_path = os.path.join('recordings', os.path.basename(file_path))
            shutil.copyfile(file_path, target_file_path)
            self.add_recording(target_file_path)
        else:
            QMessageBox.warning(self, "File Type", "The selected file is not a supported audio or video type.")
    def handle_transcoding_error(self, error_message):
        QMessageBox.critical(self, "Transcoding Error", error_message)
    def on_download_youtube_clicked(self):
        self.download_dialog = YouTubeDownloadDialog(self)
        self.download_dialog.download_requested.connect(self.handle_youtube_download)
        self.download_dialog.exec_()  # This will open the dialog to enter the URL
    def handle_youtube_download_error(self, error_message):
        QMessageBox.critical(self, "Download Error", error_message)

    def handle_youtube_download(self, url):
        self.youtube_thread = YouTubeDownloadThread(url)
        self.youtube_thread.completed.connect(self.start_transcoding)
        self.youtube_thread.error.connect(self.handle_youtube_download_error)
        self.youtube_thread.start()

    def start_transcoding(self, file_path):
        self.transcoding_thread = TranscodingThread(file_path, target_format='mp3')
        self.transcoding_thread.completed.connect(self.add_recording)
        self.transcoding_thread.error.connect(self.handle_transcoding_error)
        self.transcoding_thread.start()

    def handle_transcoding_error(self, error_message):
        QMessageBox.critical(self, "Transcoding Error", error_message)



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
    def showRightClickMenu(self, position):
        # Get the global position for showing the context menu
        global_pos = self.recordings_list.viewport().mapToGlobal(position)

        # Create the context menu
        menu = QMenu()
        delete_action = menu.addAction("Delete")

        # Show the context menu and get the selected action
        action = menu.exec_(global_pos)

        # If delete is clicked, call the method to delete the item
        if action == delete_action:
            self.deleteRecording(position)

    @staticmethod
    def is_video_file(file_path):
        video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.webm']
        file_extension = os.path.splitext(file_path)[1].lower()
        return file_extension in video_extensions

    @staticmethod
    def is_audio_file(file_path):
        audio_extensions = ['.mp3', '.wav', '.aac', '.flac', '.ogg', '.m4a']
        file_extension = os.path.splitext(file_path)[1].lower()
        return file_extension in audio_extensions

    def deleteRecording(self, position):
        # Get the item at the clicked position
        item = self.recordings_list.itemAt(position)
        if item is None:
            return  # No item at the position

        # Confirm deletion with the user
        reply = QMessageBox.question(self, 'Delete Recording',
                                     'Are you sure you want to delete this recording?',
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            # Proceed with deletion
            row = self.recordings_list.row(item)
            full_file_path = item.data(Qt.UserRole)['full_path']
            # Optionally, delete the file from the filesystem
            os.remove(full_file_path)
            self.recordings_list.takeItem(row)


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


        layout.addLayout(v_layout, 5)

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
        self.recent_recordings_widget.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        self.voice_recorder_widget = VoiceRecorderWidget()  # The voice recorder widget
        self.main_transcription_widget = MainTranscriptionWidget()

        # Add the RecentRecordingsWidget and VoiceRecorderWidget to left_layout
        self.left_layout.addWidget(self.recent_recordings_widget,5) #1 is stretch
        self.left_layout.addStretch(1) #spacer
        self.left_layout.addWidget(self.voice_recorder_widget,1) #0 is stretch

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