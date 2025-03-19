import datetime
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QHBoxLayout, QProgressBar, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QFont, QColor
import os
import logging
from app.database import create_connection, update_recording
from app.utils import resource_path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class EditableLineEdit(QLineEdit):
    editingFinished = pyqtSignal(str)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setReadOnly(True)  # Start as read-only
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("border: none; background: transparent;")

    def mouseDoubleClickEvent(self, event):
        """Handle double-click to edit."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.setReadOnly(False)  # Allow editing
            self.setCursor(Qt.CursorShape.IBeamCursor)
            self.selectAll()
            super().mouseDoubleClickEvent(event)  # Pass the event to the base class

    def focusOutEvent(self, event):
        """Handle focus out to save changes."""
        if not self.isReadOnly():
            self.setReadOnly(True)  # Make read-only again when focus is lost
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.editingFinished.emit(self.text())  # Emit the signal with the new text
        super().focusOutEvent(event)


class StatusIndicator(QWidget):
    """Visual indicator for recording status (has transcript, processed, etc)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self._has_transcript = False
        self._has_processed = False

    def set_status(self, has_transcript, has_processed):
        """Set the status of the indicator."""
        self._has_transcript = has_transcript
        self._has_processed = has_processed
        self.update()  # Trigger repaint

    def paintEvent(self, event):
        """Paint the indicator based on status."""
        import math
        from PyQt6.QtGui import QPainter, QPen, QBrush

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Define colors
        if self._has_transcript and self._has_processed:
            # Both transcript and processed
            color = QColor("#4CAF50")  # Green
            tooltip = "Has transcript and processed text"
        elif self._has_transcript:
            # Only transcript
            color = QColor("#2196F3")  # Blue
            tooltip = "Has transcript"
        else:
            # No transcript
            color = QColor("#9E9E9E")  # Gray
            tooltip = "No transcript"

        self.setToolTip(tooltip)

        # Draw circle
        painter.setPen(QPen(color, 1))
        painter.setBrush(QBrush(color))
        painter.drawEllipse(2, 2, 12, 12)


class RecordingListItem(QWidget):
    def __init__(self, id, filename, file_path, date_created, duration,
                 raw_transcript, processed_text, raw_transcript_formatted=None,
                 processed_text_formatted=None, *args, **kwargs):
        super(RecordingListItem, self).__init__(*args, **kwargs)

        # Store recording data
        self.raw_transcript = raw_transcript or ""
        self.processed_text = processed_text or ""
        self.duration = duration
        self.filename = filename
        self.id = id
        self.date_created = date_created
        self.file_path = file_path
        self.raw_transcript_formatted_data = raw_transcript_formatted
        self.processed_text_formatted_data = processed_text_formatted

        # Extract the filename without the extension
        self.filename_no_ext = os.path.splitext(self.filename)[0]

        # Create the UI
        self.setup_ui()

        # Initialize metadata
        self.metadata = {
            'id': self.id,
            'full_path': self.file_path,
            'filename': self.filename_no_ext,
            'date_created': self.date_created,
            'duration': self.duration
        }

        # Update relative time initially
        self.update_relative_time()

    def setup_ui(self):
        """Set up the user interface for the recording item."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # Status indicator
        self.status_indicator = StatusIndicator(self)
        self.status_indicator.set_status(bool(self.raw_transcript), bool(self.processed_text))

        # File icon based on file type
        icon_label = QLabel()
        icon_path = self.get_icon_for_file()
        icon_label.setPixmap(QIcon(resource_path(icon_path)).pixmap(QSize(24, 24)))

        # Left section for icon and status
        left_section = QVBoxLayout()
        left_section.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignCenter)
        left_section.addWidget(self.status_indicator, alignment=Qt.AlignmentFlag.AlignCenter)
        left_section.addStretch()

        # Center section for filename and date
        center_section = QVBoxLayout()

        # Editable filename
        self.name_editable = EditableLineEdit(self.filename_no_ext)
        self.name_editable.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.name_editable.editingFinished.connect(self.on_name_editing_finished)
        center_section.addWidget(self.name_editable)

        # Date and transcript status
        self.date_label = QLabel()
        self.date_label.setFont(QFont("Arial", 9))
        self.date_label.setStyleSheet("color: #666;")
        center_section.addWidget(self.date_label)

        # Transcript status label
        self.status_label = QLabel()
        self.status_label.setFont(QFont("Arial", 9, QFont.Weight.Light, italic=True))
        self.update_status_label()
        center_section.addWidget(self.status_label)

        center_section.addStretch()

        # Right section for duration
        right_section = QVBoxLayout()
        self.duration_label = QLabel(self.duration)
        self.duration_label.setFont(QFont("Arial", 10))
        self.duration_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        right_section.addWidget(self.duration_label)
        right_section.addStretch()

        # Assemble layout
        main_layout.addLayout(left_section, 0)
        main_layout.addSpacing(10)
        main_layout.addLayout(center_section, 1)
        main_layout.addLayout(right_section, 0)

        # Set fixed height for consistent look
        self.setMinimumHeight(70)
        # HERE IS THE FIXED LINE:
        self.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)

    def get_icon_for_file(self):
        """Get appropriate icon based on file type."""
        extension = os.path.splitext(self.file_path)[1].lower()

        if extension in ['.mp3', '.wav', '.m4a', '.ogg', '.flac']:
            return 'icons/audio.svg'
        elif extension in ['.mp4', '.avi', '.mov', '.mkv']:
            return 'icons/video.svg'
        else:
            return 'icons/file.svg'

    def update_status_label(self):
        """Update the status label based on transcript and processing state."""
        if self.raw_transcript and self.processed_text:
            self.status_label.setText("Transcribed and processed")
            self.status_label.setStyleSheet("color: #4CAF50;")  # Green
        elif self.raw_transcript:
            self.status_label.setText("Transcribed")
            self.status_label.setStyleSheet("color: #2196F3;")  # Blue
        else:
            self.status_label.setText("Not transcribed")
            self.status_label.setStyleSheet("color: #9E9E9E;")  # Gray

    def update_relative_time(self):
        """Update the date label with relative time (e.g., "2 hours ago")."""
        try:
            created_date = datetime.datetime.strptime(self.date_created, "%Y-%m-%d %H:%M:%S")
            now = datetime.datetime.now()
            diff = now - created_date

            if diff.days > 7:
                # More than a week, show date
                self.date_label.setText(created_date.strftime("%b %d, %Y"))
            elif diff.days > 0:
                # Days
                days = diff.days
                self.date_label.setText(f"{days} {'day' if days == 1 else 'days'} ago")
            elif diff.seconds >= 3600:
                # Hours
                hours = diff.seconds // 3600
                self.date_label.setText(f"{hours} {'hour' if hours == 1 else 'hours'} ago")
            elif diff.seconds >= 60:
                # Minutes
                minutes = diff.seconds // 60
                self.date_label.setText(f"{minutes} {'minute' if minutes == 1 else 'minutes'} ago")
            else:
                # Seconds or just now
                self.date_label.setText("Just now")
        except Exception as e:
            logging.error(f"Error updating relative time: {e}")
            self.date_label.setText(self.date_created)

    def get_id(self):
        """Get the recording ID."""
        return self.metadata['id']

    def get_raw_transcript(self):
        """Get the raw transcript text."""
        return self.raw_transcript

    def get_processed_text(self):
        """Get the processed text."""
        return self.processed_text

    def has_transcript(self):
        """Check if the recording has a transcript."""
        return bool(self.raw_transcript)

    def has_processed_text(self):
        """Check if the recording has processed text."""
        return bool(self.processed_text)

    def on_name_editing_finished(self, new_name):
        """Handle editing of the recording name."""
        # Check if name actually changed
        if new_name != self.filename_no_ext:
            # Update the database with the new name
            db_path = resource_path("./database/database.sqlite")
            conn = create_connection(db_path)
            if conn is not None:
                try:
                    update_recording(conn, self.id, filename=new_name)

                    # Update the UI and internal state
                    self.filename = new_name
                    self.filename_no_ext = new_name
                    self.metadata['filename'] = self.filename_no_ext

                    # Log the change
                    logging.info(f"Recording {self.id} renamed to {new_name}")
                except Exception as e:
                    logging.error(f"Error updating recording name: {e}")
                finally:
                    conn.close()
            else:
                logging.error("Error! Cannot connect to the database.")