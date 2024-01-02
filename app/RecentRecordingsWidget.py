import traceback
import datetime
from PyQt6.QtCore import (
    pyqtSignal, QSize, Qt, QPropertyAnimation, QEasingCurve, QFile,
)
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout,  QMessageBox,
    QWidget,  QLabel, QListWidget,
     QMenu, QListWidgetItem
)
import os
from app.RecordingListItem import RecordingListItem

from app.database import create_connection, get_all_recordings, create_db, create_recording, update_recording, delete_recording

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

            item = QListWidgetItem(self.recordings_list)
            item.setSizeHint(recording_item_widget.sizeHint())

            self.recordings_list.addItem(item)
            self.recordings_list.setItemWidget(item, recording_item_widget)

            item.setData(Qt.ItemDataRole.UserRole, recording_item_widget.metadata)

        except Exception as e:
            print(f"An error occurred: {e}")
            traceback.print_exc()


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
        global_pos = self.recordings_list.viewport().mapToGlobal(position)

        menu = QMenu()
        delete_action = menu.addAction("Delete")

        action = menu.exec(global_pos)

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
            id, filename, file_path, date_created, duration, raw_transcript, processed_text, raw_transcript_formatted, processed_text_formatted = recording
            self.add_recording_to_list(id, filename, file_path, date_created, duration, raw_transcript, processed_text)

    def add_recording_to_list(self, id, filename, file_path, date_created, duration, raw_transcript, processed_text):
        recording_item_widget = RecordingListItem(id, filename, file_path, date_created, duration, raw_transcript, processed_text)

        # Set metadata
        recording_item_widget.metadata = {
            'id': id,
            'filename': filename,
            'full_path': file_path,
            'date_created': date_created,
            'duration': duration
        }

        item = QListWidgetItem(self.recordings_list)
        item.setSizeHint(recording_item_widget.sizeHint())

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
