import datetime
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QHBoxLayout
from PyQt6.QtCore import Qt
import os
from pydub import AudioSegment

class RecordingListItem(QWidget):
    def __init__(self, full_file_path, *args, **kwargs):
        super(RecordingListItem, self).__init__(*args, **kwargs)
        self.raw_transcript = ""
        self.processed_text = ""

        # Extract the filename without the extension
        filename = os.path.basename(full_file_path)
        filename_no_ext = os.path.splitext(filename)[0]

        # Extract the creation date and duration from the file metadata
        creation_date = datetime.datetime.fromtimestamp(
            os.path.getmtime(full_file_path)
        ).strftime("%Y-%m-%d %H:%M:%S")
        audio = AudioSegment.from_file(full_file_path)
        duration = str(datetime.timedelta(milliseconds=len(audio))).split('.')[0]

        self.name_editable = EditableLineEdit(filename_no_ext)
        self.name_editable.editingFinished.connect(self.finishEditing)
        self.date_label = QLabel(creation_date)
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
            'full_path': full_file_path,
            'filename': filename_no_ext,
            'date': creation_date,
            'duration': duration
        }

    def set_raw_transcript(self, transcript):
        print('hello')
        self.raw_transcript = transcript
        print(self.raw_transcript)

    def get_raw_transcript(self):
        return self.raw_transcript

    def set_processed_text(self, text):
        self.processed_text = text

    def get_processed_text(self):
        return self.processed_text

    def finishEditing(self):
        new_name = self.name_editable.text()
        # Here you would implement the rename logic

class EditableLineEdit(QLineEdit):
    def __init__(self, *args, **kwargs):
        super(EditableLineEdit, self).__init__(*args, **kwargs)
        self.setReadOnly(True)  # Start as read-only

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setReadOnly(False)  # Allow editing
            self.selectAll()  # Optionally select all text to make editing easier
            super(EditableLineEdit, self).mouseDoubleClickEvent(event)  # Pass the event to the base class

    def focusOutEvent(self, event):
        self.setReadOnly(True)  # Make read-only again when focus is lost
        super(EditableLineEdit, self).focusOutEvent(event)  # Pass the event to the base class