import datetime
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QHBoxLayout
from PyQt6.QtCore import Qt,pyqtSignal
import os
from app.database import create_connection,update_recording


class RecordingListItem(QWidget):
    def __init__(self, id, filename, file_path, date_created, duration, raw_transcript, processed_text, *args, **kwargs):
        super(RecordingListItem, self).__init__(*args, **kwargs)
        self.raw_transcript = raw_transcript
        self.processed_text = processed_text
        self.duration = duration
        self.filename = filename
        self.id = id
        self.date_created = date_created
        self.file_path = file_path
        # Extract the filename without the extension
       # filename = os.path.basename(full_file_path)
        self.filename_no_ext = os.path.splitext(self.filename)[0]

        # Extract the creation date and duration from the file metadata
        self.creation_date = datetime.datetime.fromtimestamp(
            os.path.getmtime(self.file_path)
        ).strftime("%Y-%m-%d %H:%M:%S")

        self.name_editable = EditableLineEdit(self.filename_no_ext)
        #self.name_editable.editingFinished.connect(self.finishEditing)
        self.date_label = QLabel(self.creation_date)
        self.duration_label = QLabel(duration)

        self.name_editable.setStyleSheet(
            "QLineEdit { color: grey; font-size: 16px; border: none; background: transparent; font-family: Roboto; }")
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
        self.duration_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.name_editable.editingFinished.connect(self.on_name_editing_finished)

        self.metadata = {
            'id': self.id,
            'full_path': self.file_path,
            'filename': self.filename_no_ext,
            'date': self.creation_date,
            'duration': self.duration
        }


    def get_id(self):
        return self.metadata['id']

    def on_name_editing_finished(self, new_name):
        # Check if name actually changed
        if new_name != self.filename_no_ext:
            # Update the database with the new name
            conn = create_connection("./database/database.sqlite")
            if conn is not None:
                update_recording(conn, self.id, filename=new_name)
                conn.close()
            else:
                print("Error! Cannot connect to the database.")
            # Update the UI and internal state if necessary
            self.filename = new_name
            self.filename_no_ext = os.path.splitext(new_name)[0]
            self.metadata['filename'] = self.filename_no_ext  # Update the metadata as well

class EditableLineEdit(QLineEdit):
    editingFinished = pyqtSignal(str)
    def __init__(self, *args, **kwargs):
        super(EditableLineEdit, self).__init__(*args, **kwargs)
        self.setReadOnly(True)  # Start as read-only

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setReadOnly(False)  # Allow editing
            self.selectAll()
            super(EditableLineEdit, self).mouseDoubleClickEvent(event)  # Pass the event to the base class

    def focusOutEvent(self, event):
        if not self.isReadOnly():
            self.setReadOnly(True)  # Make read-only again when focus is lost
            self.editingFinished.emit(self.text())  # Emit the signal with the new text
        super().focusOutEvent(event)