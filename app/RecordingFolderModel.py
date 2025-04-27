import logging
from datetime import datetime, timedelta
from PyQt6.QtCore import Qt, QSortFilterProxyModel
from PyQt6.QtGui import QStandardItemModel, QStandardItem

logger = logging.getLogger("transcribrr")


class RecordingFolderModel(QStandardItemModel):
    """Model for storing the recording folder structure."""

    # Custom roles for storing data
    ITEM_TYPE_ROLE = Qt.ItemDataRole.UserRole + 1
    ITEM_ID_ROLE = Qt.ItemDataRole.UserRole + 2
    FULL_TRANSCRIPT_ROLE = Qt.ItemDataRole.UserRole + 3
    HAS_TRANSCRIPT_ROLE = Qt.ItemDataRole.UserRole + 4
    DATE_CREATED_ROLE = Qt.ItemDataRole.UserRole + 5
    FILE_PATH_ROLE = Qt.ItemDataRole.UserRole + 6
    DURATION_ROLE = Qt.ItemDataRole.UserRole + 7
    FILE_TYPE_ROLE = Qt.ItemDataRole.UserRole + 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_icon = None
        self.video_icon = None
        self.file_icon = None
        self.folder_icon = None
        self.folder_open_icon = None

        # Maps to quickly look up items (for selection restoration, etc.)
        self.item_map = {}  # (type, id) -> QStandardItem

    def set_icons(
        self, folder_icon, folder_open_icon, audio_icon, video_icon, file_icon
    ):
        """Set model icons for different item types."""
        self.folder_icon = folder_icon
        self.folder_open_icon = folder_open_icon
        self.audio_icon = audio_icon
        self.video_icon = video_icon
        self.file_icon = file_icon

    def add_folder_item(self, folder_data, parent_item=None):
        """Add folder item to the model."""
        # Create a new item for the folder
        folder_item = QStandardItem()
        folder_item.setText(folder_data["name"])
        folder_item.setIcon(self.folder_icon)

        # Store folder metadata in item roles
        folder_item.setData("folder", self.ITEM_TYPE_ROLE)
        folder_item.setData(folder_data["id"], self.ITEM_ID_ROLE)

        # Store for quick lookup
        self.item_map[("folder", folder_data["id"])] = folder_item

        # Add to the model
        if parent_item is None:
            self.appendRow(folder_item)
        else:
            parent_item.appendRow(folder_item)

        return folder_item

    def add_recording_item(self, recording_data, parent_item):
        """Add recording item to the model."""
        # Create a new item for the recording
        recording_item = QStandardItem()

        # Clear the display text to prevent overlapping with custom widget
        # Empty text to avoid overlap with custom widget
        recording_item.setText("")
        # Still set file type icon as the custom widget will be overlaid
        # Choose icon based on file type
        file_type = self._determine_file_type(recording_data[2])  # File path
        if file_type == "audio":
            recording_item.setIcon(self.audio_icon)
        elif file_type == "video":
            recording_item.setIcon(self.video_icon)
        else:
            recording_item.setIcon(self.file_icon)

        # Store recording metadata in item roles
        recording_item.setData("recording", self.ITEM_TYPE_ROLE)
        recording_item.setData(
            recording_data[0], self.ITEM_ID_ROLE)  # recording ID
        recording_item.setData(
            recording_data[2], self.FILE_PATH_ROLE)  # File path

        # Store transcript data if available
        raw_transcript = recording_data[4] or ""
        processed_transcript = recording_data[5] or ""
        has_transcript = bool(raw_transcript.strip()
                              or processed_transcript.strip())

        # Combine all text for searching
        full_text_for_search = (
            f"{recording_data[1]} {raw_transcript} {processed_transcript}"
        )
        recording_item.setData(full_text_for_search, self.FULL_TRANSCRIPT_ROLE)
        recording_item.setData(has_transcript, self.HAS_TRANSCRIPT_ROLE)

        # Store date created - needed for filtering by date
        try:
            date_str = recording_data[3]
            date_obj = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            recording_item.setData(date_obj, self.DATE_CREATED_ROLE)
        except (ValueError, TypeError) as e:
            logger.warning(
                f"Failed to parse date for recording {recording_data[0]}: {e}"
            )
            recording_item.setData(
                datetime.now(), self.DATE_CREATED_ROLE)  # Fallback

        # Store for quick lookup
        self.item_map[("recording", recording_data[0])] = recording_item

        # Add to the model under parent
        parent_item.appendRow(recording_item)
        return recording_item

    def _determine_file_type(self, file_path):
        """Determine file type based on extension."""
        if not file_path:
            return "unknown"

        file_path = file_path.lower()
        audio_extensions = [".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg"]
        video_extensions = [".mp4", ".mov", ".avi", ".mkv", ".webm"]

        for ext in audio_extensions:
            if file_path.endswith(ext):
                return "audio"

        for ext in video_extensions:
            if file_path.endswith(ext):
                return "video"

        return "unknown"

    def get_item_by_id(self, item_id, item_type):
        """Get model item by ID and type."""
        key = (item_type, item_id)
        return self.item_map.get(key)

    def clear_model(self):
        """Clear all items from the model."""
        self.item_map.clear()
        self.removeRows(0, self.rowCount())


class RecordingFilterProxyModel(QSortFilterProxyModel):
    """Filter proxy model for recordings and folders."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.filter_text = ""
        self.filter_criteria = "All"
        self.setRecursiveFilteringEnabled(True)

    def setFilterText(self, text):
        """Set text to filter by."""
        self.filter_text = text.lower()
        self.invalidateFilter()

    def setFilterCriteria(self, criteria):
        """Set criteria to filter by."""
        self.filter_criteria = criteria
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        """Determine if a row should be visible based on filters."""
        source_index = self.sourceModel().index(source_row, 0, source_parent)
        if not source_index.isValid():
            return False

        # Get the source item
        source_item = self.sourceModel().itemFromIndex(source_index)
        if not source_item:
            return False

        # Get item type
        item_type = source_item.data(RecordingFolderModel.ITEM_TYPE_ROLE)
        item_id = source_item.data(RecordingFolderModel.ITEM_ID_ROLE)

        # Special case: always show root folder
        if item_type == "folder" and item_id == -1:
            return True

        # Handle folders
        if item_type == "folder":
            # Check if folder name matches filter text
            folder_name = source_item.text().lower()
            if self.filter_text and self.filter_text in folder_name:
                return True

            # Check if any child matches the filter
            # This is important to keep the folder structure intact
            for row in range(source_item.rowCount()):
                child_index = self.sourceModel().index(row, 0, source_index)
                if self.filterAcceptsRow(row, source_index):
                    return True

            # If we got here, neither folder name nor children match
            return False

        # Handle recordings
        elif item_type == "recording":
            # First, check text match
            if self.filter_text:
                # Get full text (filename + transcript) for searching
                full_text = (
                    source_item.data(
                        RecordingFolderModel.FULL_TRANSCRIPT_ROLE) or ""
                ).lower()
                if self.filter_text not in full_text:
                    return False  # Text doesn't match

            # Then check criteria match
            if self.filter_criteria != "All":
                if self.filter_criteria == "Has Transcript":
                    has_transcript = source_item.data(
                        RecordingFolderModel.HAS_TRANSCRIPT_ROLE
                    )
                    if not has_transcript:
                        return False

                elif self.filter_criteria == "No Transcript":
                    has_transcript = source_item.data(
                        RecordingFolderModel.HAS_TRANSCRIPT_ROLE
                    )
                    if has_transcript:
                        return False

                elif self.filter_criteria in ["Recent (24h)", "This Week"]:
                    date_created = source_item.data(
                        RecordingFolderModel.DATE_CREATED_ROLE
                    )
                    if not date_created:
                        return False

                    now = datetime.now()

                    if self.filter_criteria == "Recent (24h)":
                        seconds_diff = (now - date_created).total_seconds()
                        if seconds_diff >= 86400:  # 24 hours in seconds
                            return False

                    elif self.filter_criteria == "This Week":
                        # Get start of current week (Monday)
                        start_of_week = now.replace(
                            hour=0, minute=0, second=0, microsecond=0
                        )
                        start_of_week = start_of_week - \
                            timedelta(days=now.weekday())
                        if date_created < start_of_week:
                            return False

            # If we got here, the recording matches all filters
            return True

        # Unknown item type, hide it
        return False
