import datetime
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QHBoxLayout
from PyQt6.QtCore import Qt
import os
from pydub import AudioSegment

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
        self.name_editable.editingFinished.connect(self.finishEditing)
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

        # Store metadata for later use
        self.metadata = {
            'id': self.id,
            'full_path': self.file_path,
            'filename': self.filename_no_ext,
            'date': self.creation_date,
            'duration': self.duration
        }

    def set_raw_transcript(self, transcript):
        self.raw_transcript = transcript

    def get_raw_transcript(self):
        return self.raw_transcript

    def set_processed_text(self, text):
        self.processed_text = text

    def get_processed_text(self):
        return self.processed_text

    def finishEditing(self):
        new_name = self.name_editable.text()
    def get_id(self):
        return self.metadata['id']

class EditableLineEdit(QLineEdit):
    def __init__(self, *args, **kwargs):
        super(EditableLineEdit, self).__init__(*args, **kwargs)
        self.setReadOnly(True)  # Start as read-only

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setReadOnly(False)  # Allow editing
            self.selectAll()
            super(EditableLineEdit, self).mouseDoubleClickEvent(event)  # Pass the event to the base class

    def focusOutEvent(self, event):
        self.setReadOnly(True)  # Make read-only again when focus is lost
        super(EditableLineEdit, self).focusOutEvent(event)