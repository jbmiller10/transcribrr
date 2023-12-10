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


# class YouTubeDownloadDialog(QDialog):
#
#     download_requested = pyqtSignal(str)
#
#     def __init__(self, parent=None):
#         super().__init__(parent)
#         self.layout = QVBoxLayout(self)
#         self.url_input = QLineEdit(self)
#         self.layout.addWidget(self.url_input)
#
#         self.download_button = QPushButton("Download", self)
#         self.download_button.clicked.connect(self.on_download_clicked)
#         self.layout.addWidget(self.download_button)
#
#     def on_download_clicked(self):
#         url = self.url_input.text()
#         if validate_url(url):
#             self.download_requested.emit(url)
#             self.accept()
#         else:
#             QMessageBox.warning(self, "Invalid URL", "The provided URL is not a valid YouTube URL.")

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
        self.recordings_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)


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




        self.voice_recorder_widget = VoiceRecorderWidget()  # The voice recorder widget

        # Set up the animation for the voice recorder widget
        self.voiceRecorderAnimation = QPropertyAnimation(self.voice_recorder_widget, b"maximumHeight")
        self.voiceRecorderAnimation.setDuration(500)  # Animation duration in milliseconds
        self.voiceRecorderAnimation.setEasingCurve(QEasingCurve.Type.InOutQuad)  # Smooth easing curve for the animation

        # Set initial visibility state and height
        self.voice_recorder_widget.setMaximumHeight(0)  # Start hidden
        self.voice_recorder_widget.setVisible(False)

        #self.buttonLayout.addWidget(self.add_button)x
        ##add to buttonlayout
        #self.buttonLayout.addWidget(self.add_button)
        #self.buttonLayout.addWidget(self.download_youtube_button)
        #self.buttonLayout.addWidget(self.record_new_button)
        #buttonSpacer = QSpacerItem(50,50, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        #self.buttonLayout.addItem(buttonSpacer)
        #self.recordings_list.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self.layout.addWidget(self.header_label)
        self.layout.addWidget(self.recordings_list,15)
        #self.layout.addStretch(1)
        self.layout.addWidget(self.voice_recorder_widget, 0)
        verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        self.layout.addItem(verticalSpacer)
        self.layout.addLayout(self.buttonLayout)

        self.recordings_list.itemClicked.connect(self.recording_clicked)
        #self.download_youtube_button.clicked.connect(self.on_download_youtube_clicked)
        #self.add_button.clicked.connect(self.on_add_button_clicked)

        # Right click context menu for delete
        self.recordings_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.recordings_list.customContextMenuRequested.connect(self.showRightClickMenu)
        #self.voice_recorder_widget.recordingCompleted.connect(self.onRecordingCompleted)

        self.animationFinishedConnected = False  # Flag to track signal connection

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
        self.setGeometry(100, 100, 1350, 768)

        # Create instances of widgets
        self.control_panel = ControlPanelWidget(self)
        self.recent_recordings_widget = RecentRecordingsWidget()
        self.voice_recorder_widget = VoiceRecorderWidget()
        self.main_transcription_widget = MainTranscriptionWidget()

        # Connect signals from the ControlPanelWidget
        #self.control_panel.upload_clicked.connect(self.on_upload_button_clicked)
        #elf.control_panel.youtube_clicked.connect(self.on_youtube_button_clicked)
        #self.control_panel.record_clicked.connect(self.on_record_button_clicked)

        #self.recent_recordings_widget = RecentRecordingsWidget()
        self.voice_recorder_widget = VoiceRecorderWidget()
        self.voice_recorder_widget.setMaximumHeight(0)
        self.voice_recorder_widget.setVisible(False)

        # Connect signals
        #self.controls_widget.recordButtonPressed.connect(self.on_record_button_press)
        #self.controls_widget.toggleVoiceRecorderRequest.connect(self.toggleVoiceRecorderVisibility)

        # Set up the central widget and its layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)

        # Create a QSplitter to manage the layout of the left and right sections
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_layout.addWidget(self.splitter)

        # Layout for the left side section
        self.left_layout = QVBoxLayout()
        self.left_layout.addWidget(self.recent_recordings_widget)
        self.left_layout.addWidget(self.control_panel)
        self.left_layout.addWidget(self.voice_recorder_widget)

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

        # Set the initial side ratios of the splitter (e.g., 1:2)
        self.splitter.setSizes([400, 800])

        # Set status bar for the window, initially hidden
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.setVisible(False)

        # Set the initial style for the window
        self.set_style()

    def toggleVoiceRecorderVisibility(self):
        # Check if the recorder is visible and configure the animation accordingly
        is_visible = self.voice_recorder_widget.isVisible()

        # Create an animation object
        self.voiceRecorderAnimation = QPropertyAnimation(self.voice_recorder_widget, b"maximumHeight")
        self.voiceRecorderAnimation.setDuration(500)  # Animation duration in milliseconds
        self.voiceRecorderAnimation.setEasingCurve(QEasingCurve.Type.InOutQuad)  # Easing curve for smooth animation

        # Determine the start and end values based on whether the widget is currently visible
        start_value = self.voice_recorder_widget.maximumHeight() if is_visible else 0
        end_value = self.voice_recorder_widget.sizeHint().height() if not is_visible else 0

        self.voiceRecorderAnimation.setStartValue(start_value)
        self.voiceRecorderAnimation.setEndValue(end_value)

        # Ensure the widget is visible before starting the animation when showing
        if not is_visible:
            self.voice_recorder_widget.setVisible(True)

        self.voiceRecorderAnimation.finished.connect(self.on_voiceRecorderAnimationFinished)

        # Start the animation
        self.voiceRecorderAnimation.start()

    def on_voiceRecorderAnimationFinished(self):
        # Hide or show the widget based on the final state after the animation
        if self.voiceRecorderAnimation.endValue() == 0:
            self.voice_recorder_widget.setVisible(False)

        # Disconnect signal to avoid calling this slot multiple times
        self.voiceRecorderAnimation.finished.disconnect(self.on_voiceRecorderAnimationFinished)

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

    def toggleVoiceRecorderVisibility(self):
        # Check the flag before disconnecting the finished signal
        if self.animationFinishedConnected:
            self.voiceRecorderAnimation.finished.disconnect()
            self.animationFinishedConnected = False

        is_visible = self.voice_recorder_widget.isVisible()
        start_value = self.voice_recorder_widget.maximumHeight()
        end_value = 0 if is_visible else self.voice_recorder_widget.sizeHint().height()

        self.voiceRecorderAnimation.setStartValue(start_value)
        self.voiceRecorderAnimation.setEndValue(end_value)

        if not is_visible:
            self.voice_recorder_widget.setVisible(True)

        if is_visible:
            self.voiceRecorderAnimation.finished.connect(self.hideVoiceRecorder)
            self.animationFinishedConnected = True
        else:
            self.voiceRecorderAnimation.finished.connect(self.showVoiceRecorder)
            self.animationFinishedConnected = True

        self.voiceRecorderAnimation.start()

    def hideVoiceRecorder(self):
        self.voice_recorder_widget.setVisible(False)
        if self.animationFinishedConnected:
            self.voiceRecorderAnimation.finished.disconnect()
            self.animationFinishedConnected = False

    def showVoiceRecorder(self):
        if self.animationFinishedConnected:
            self.voiceRecorderAnimation.finished.disconnect()
            self.animationFinishedConnected = False

    def onRecordingCompleted(self, file_name):
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
