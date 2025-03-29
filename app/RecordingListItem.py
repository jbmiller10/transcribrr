import datetime
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QHBoxLayout, QProgressBar, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QFont, QColor
import os
import logging
# Removed direct DB import, DatabaseManager will handle updates
# from app.database import create_connection, update_recording
from app.utils import resource_path
from app.FolderManager import FolderManager # Keep for folder info

# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s') # Configured in main
logger = logging.getLogger('transcribrr')


class EditableLineEdit(QLineEdit):
    editingFinished = pyqtSignal(str) # Signal unchanged

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setReadOnly(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Simpler styling, rely on ThemeManager mostly
        self.setStyleSheet("border: none; background: transparent; padding: 1px;")

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setReadOnly(False)
            self.setCursor(Qt.CursorShape.IBeamCursor)
            self.selectAll()
            self.setStyleSheet("border: 1px solid gray; background: white; padding: 0px;") # Indicate editing
            super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event):
        if not self.isReadOnly():
            self.setReadOnly(True)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setStyleSheet("border: none; background: transparent; padding: 1px;") # Restore style
            self.editingFinished.emit(self.text()) # Emit signal
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
         """Commit edit on Enter/Return, cancel on Escape."""
         if not self.isReadOnly():
              if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
                   self.editingFinished.emit(self.text())
                   self.clearFocus() # This will trigger focusOutEvent to make read-only
              elif event.key() == Qt.Key.Key_Escape:
                   self.setText(self._original_text) # Restore original text (need to store it)
                   self.clearFocus()
              else:
                   super().keyPressEvent(event)
         else:
              super().keyPressEvent(event)

    def setReadOnly(self, readOnly):
        """Store original text when becoming editable."""
        if not readOnly and self.isReadOnly(): # Transitioning to editable
             self._original_text = self.text()
        super().setReadOnly(readOnly)


class StatusIndicator(QWidget):
    # (Content mostly unchanged)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self._has_transcript = False
        self._has_processed = False

    def set_status(self, has_transcript, has_processed):
        self._has_transcript = has_transcript
        self._has_processed = has_processed
        self.update()

    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter, QPen, QBrush # Local import fine here

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._has_transcript and self._has_processed:
            color = QColor("#4CAF50") # Green
            tooltip = "Has transcript and processed text"
        elif self._has_transcript:
            color = QColor("#2196F3") # Blue
            tooltip = "Has transcript"
        else:
            color = QColor("#9E9E9E") # Gray
            tooltip = "No transcript available"

        self.setToolTip(tooltip)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(2, 2, 12, 12)


class RecordingListItem(QWidget):
    # Signal emitted when the user finishes editing the name
    nameChanged = pyqtSignal(int, str) # id, new_name

    def __init__(self, id, filename, file_path, date_created, duration,
                 raw_transcript, processed_text, raw_transcript_formatted=None,
                 processed_text_formatted=None, *args, **kwargs):
        super(RecordingListItem, self).__init__(*args, **kwargs)

        # Store core data
        self.id = id
        self.filename = filename # Includes extension
        self.file_path = file_path
        self.date_created = date_created
        self.duration = duration
        self.raw_transcript = raw_transcript or ""
        self.processed_text = processed_text or ""
        self.raw_transcript_formatted_data = raw_transcript_formatted # Keep potentially large data
        self.processed_text_formatted_data = processed_text_formatted # Keep potentially large data

        # Filename without extension for editing
        self.filename_no_ext = os.path.splitext(self.filename)[0]

        self.folders = []
        self.load_folders() # Initial load

        self.setup_ui()

        # Update relative time initially and periodically
        self.update_relative_time()
        self.timer = self.startTimer(60000) # Update every minute

    def timerEvent(self, event):
        """Handle timer event to update relative time."""
        self.update_relative_time()
        event.accept()

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8) # Consistent margins
        main_layout.setSpacing(8) # Consistent spacing

        # Status indicator & Icon
        left_section = QVBoxLayout()
        left_section.setSpacing(4)
        icon_label = QLabel()
        icon_path = self.get_icon_for_file()
        icon_label.setPixmap(QIcon(resource_path(icon_path)).pixmap(QSize(24, 24)))
        self.status_indicator = StatusIndicator(self)
        self.status_indicator.set_status(bool(self.raw_transcript), bool(self.processed_text))
        left_section.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        left_section.addWidget(self.status_indicator, alignment=Qt.AlignmentFlag.AlignHCenter)
        left_section.addStretch()

        # Center section: Name, Date, Status, Folders
        center_section = QVBoxLayout()
        center_section.setSpacing(2) # Less spacing between text lines
        self.name_editable = EditableLineEdit(self.filename_no_ext)
        self.name_editable.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        # Connect the internal signal to the class signal
        self.name_editable.editingFinished.connect(self.handle_name_editing_finished)
        center_section.addWidget(self.name_editable)

        self.date_label = QLabel()
        self.date_label.setFont(QFont("Arial", 9))
        self.date_label.setStyleSheet("color: #666;") # Style hint
        center_section.addWidget(self.date_label)

        self.status_label = QLabel()
        self.status_label.setFont(QFont("Arial", 9, QFont.Weight.Light, italic=True))
        self.update_status_label()
        center_section.addWidget(self.status_label)

        self.folder_label = QLabel()
        self.folder_label.setFont(QFont("Arial", 9))
        self.folder_label.setStyleSheet("color: #666; font-style: italic;") # Style hint
        self.update_folder_label()
        center_section.addWidget(self.folder_label)
        center_section.addStretch()

        # Right section: Duration
        right_section = QVBoxLayout()
        self.duration_label = QLabel(self.duration)
        self.duration_label.setFont(QFont("Arial", 10))
        self.duration_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        right_section.addWidget(self.duration_label)
        right_section.addStretch()

        # Assemble layout
        main_layout.addLayout(left_section, 0)
        main_layout.addLayout(center_section, 1) # Allow center to stretch
        main_layout.addLayout(right_section, 0)

        self.setMinimumHeight(70)
        # Let the list view manage the width, fix the height
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def get_icon_for_file(self):
        extension = os.path.splitext(self.file_path)[1].lower()
        if extension in ['.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.aiff', '.wma']:
            return 'icons/audio.svg'
        elif extension in ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv']:
            return 'icons/video.svg'
        else:
            return 'icons/file.svg'

    def update_status_label(self):
        if self.raw_transcript and self.processed_text:
            self.status_label.setText("Transcribed & Processed")
            self.status_label.setStyleSheet("color: #4CAF50;")
        elif self.raw_transcript:
            self.status_label.setText("Transcribed")
            self.status_label.setStyleSheet("color: #2196F3;")
        else:
            self.status_label.setText("Needs Transcription")
            self.status_label.setStyleSheet("color: #9E9E9E;")
        self.status_indicator.set_status(bool(self.raw_transcript), bool(self.processed_text))

    def update_relative_time(self):
        try:
            created_date = datetime.datetime.strptime(self.date_created, "%Y-%m-%d %H:%M:%S")
            now = datetime.datetime.now()
            diff = now - created_date

            if diff.days > 7:
                time_str = created_date.strftime("%b %d, %Y")
            elif diff.days > 0:
                days = diff.days
                time_str = f"{days} day{'s' if days > 1 else ''} ago"
            elif diff.seconds >= 3600:
                hours = diff.seconds // 3600
                time_str = f"{hours} hour{'s' if hours > 1 else ''} ago"
            elif diff.seconds >= 120: # Show minutes > 2 mins ago
                minutes = diff.seconds // 60
                time_str = f"{minutes} mins ago"
            else:
                time_str = "Just now"
            self.date_label.setText(time_str)
        except Exception as e:
            logger.warning(f"Error updating relative time for {self.id}: {e}")
            self.date_label.setText(self.date_created.split()[0]) # Fallback to date part

    # --- Getters ---
    def get_id(self): return self.id
    def get_filename(self): return self.filename # Full filename with ext
    def get_filepath(self): return self.file_path
    def get_raw_transcript(self): return self.raw_transcript
    def get_processed_text(self): return self.processed_text
    def get_raw_formatted(self): return self.raw_transcript_formatted_data
    def get_processed_formatted(self): return self.processed_text_formatted_data
    def has_transcript(self): return bool(self.raw_transcript)
    def has_processed_text(self): return bool(self.processed_text)

    # --- Folder Management ---
    def load_folders(self):
        try:
            # Assuming FolderManager provides structured folder data
            folders_data = FolderManager.instance().get_folders_for_recording(self.id)
            self.folders = [{'id': f[0], 'name': f[1]} for f in folders_data] # Simplified structure
        except Exception as e:
            logger.error(f"Error loading folders for recording {self.id}: {e}")
            self.folders = []
        # Update UI after loading
        if hasattr(self, 'folder_label'): # Check if UI is initialized
             self.update_folder_label()

    def update_folder_label(self):
        if not self.folders:
            self.folder_label.setText("")
            self.folder_label.setVisible(False)
        elif len(self.folders) == 1:
            # Truncate long folder names
            folder_name = self.folders[0]['name']
            display_name = folder_name[:25] + '...' if len(folder_name) > 25 else folder_name
            self.folder_label.setText(f"Folder: {display_name}")
            self.folder_label.setToolTip(f"In folder: {folder_name}")
            self.folder_label.setVisible(True)
        else:
            folder_names = ", ".join(f['name'] for f in self.folders)
            self.folder_label.setText(f"In {len(self.folders)} folders")
            self.folder_label.setToolTip(f"In folders: {folder_names}")
            self.folder_label.setVisible(True)

    def refresh_folders(self):
        self.load_folders()

    # --- Rename Handling ---
    def handle_name_editing_finished(self, new_name_no_ext):
        """Handle editing finished signal from EditableLineEdit."""
        # Validate the new name (e.g., check for empty string, invalid chars if needed)
        new_name_no_ext = new_name_no_ext.strip()
        if not new_name_no_ext:
            # Restore original name if edited to empty
            self.name_editable.setText(self.filename_no_ext)
            logger.warning(f"Recording rename cancelled: Name cannot be empty.")
            return

        # Check if the name actually changed
        if new_name_no_ext != self.filename_no_ext:
            logger.info(f"Requesting rename for ID {self.id} to '{new_name_no_ext}'")
            # Emit signal for the parent widget (RecentRecordingsWidget) to handle DB update
            self.nameChanged.emit(self.id, new_name_no_ext)
            # Optimistically update internal state, parent should confirm/revert if DB fails
            # self.filename_no_ext = new_name_no_ext
            # self.filename = new_name_no_ext + os.path.splitext(self.filename)[1] # Update full filename too
        else:
             logger.debug(f"Recording {self.id} name unchanged.")


    # --- Update from External Data ---
    def update_data(self, data: dict):
         """Update item's data and UI, e.g., after DB update."""
         self.raw_transcript = data.get('raw_transcript', self.raw_transcript)
         self.processed_text = data.get('processed_text', self.processed_text)
         self.raw_transcript_formatted_data = data.get('raw_transcript_formatted', self.raw_transcript_formatted_data)
         self.processed_text_formatted_data = data.get('processed_text_formatted', self.processed_text_formatted_data)

         # Update filename if changed externally
         new_filename_no_ext = data.get('filename', self.filename_no_ext)
         if new_filename_no_ext != self.filename_no_ext:
              self.filename_no_ext = new_filename_no_ext
              self.filename = new_filename_no_ext + os.path.splitext(self.filename)[1]
              self.name_editable.setText(self.filename_no_ext) # Update UI

         self.update_status_label()
         self.refresh_folders() # Refresh folder display as well