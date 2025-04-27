#!/usr/bin/env python3
"""
Manual test to verify that dataChanged events during tree refresh are properly queued
and processed after the refresh completes. Tests for batch inserts functionality.
"""

import sys
import time
import logging
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import QTimer

from app.DatabaseManager import DatabaseManager
from app.FolderManager import FolderManager
from app.UnifiedFolderTreeView import UnifiedFolderTreeView

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TestWindow(QWidget):
    def __init__(self):
        super().__init__()

        # Set up UI
        self.setWindowTitle("Batch Insert Test")
        self.resize(800, 600)

        layout = QVBoxLayout(self)

        # Create DatabaseManager and FolderManager
        self.db_manager = DatabaseManager()

        folder_manager = FolderManager()
        folder_manager.attach_db_manager(self.db_manager)

        # Create tree view
        self.tree_view = UnifiedFolderTreeView(self.db_manager)
        layout.addWidget(self.tree_view)

        # Add buttons
        self.add_button = QPushButton("Add 5 Recordings (Batch)")
        self.add_button.clicked.connect(self.add_batch_recordings)
        layout.addWidget(self.add_button)

        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)

    def add_batch_recordings(self):
        """Add 5 recordings in rapid succession (< 200ms total)"""
        self.status_label.setText("Adding 5 recordings...")

        # Create recordings with minimal delay
        recordings_to_add = 5
        added_count = 0

        # Keep track of callbacks to know when all recordings are added
        self.pending_callbacks = recordings_to_add

        # Define callback function
        def on_recording_created(recording_id):
            nonlocal added_count
            added_count += 1
            self.pending_callbacks -= 1
            logger.info(f"Recording {added_count} created with ID: {recording_id}")

            if self.pending_callbacks == 0:
                self.status_label.setText(f"Added {added_count} recordings")
                # Schedule a check after a short delay to verify all recordings are visible
                QTimer.singleShot(500, self.verify_recordings)

        # Add recordings in quick succession
        for i in range(recordings_to_add):
            # Prepare test recording data
            import datetime
            filename = f"test_recording_{i+1}.mp3"
            file_path = f"/tmp/{filename}"
            date_created = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            duration = 60  # 1 minute
            original_source = file_path

            # Create recording in database
            recording_data = (filename, file_path, date_created, duration, "", "", original_source)
            self.db_manager.create_recording(recording_data, on_recording_created)

            # Very short delay to make them distinct but still rapid
            time.sleep(0.01)

    def verify_recordings(self):
        """Verify that all recordings are visible in the tree"""
        # This would need manual verification in a real scenario
        # For this test, we just log the current count of visible recordings
        recording_count = len(self.tree_view.id_to_widget)
        logger.info(f"Tree view contains {recording_count} visible recordings")
        self.status_label.setText(f"Tree view shows {recording_count} recordings")


def main():
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
