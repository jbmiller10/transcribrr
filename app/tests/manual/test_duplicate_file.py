#!/usr/bin/env python3
"""
Manual test to verify that duplicate file path errors are properly surfaced to the UI
with clear error messages in the status bar.
"""

import sys
import logging
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import Qt, QTimer

from app.DatabaseManager import DatabaseManager
from app.FolderManager import FolderManager

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TestWindow(QWidget):
    def __init__(self):
        super().__init__()
        
        # Set up UI
        self.setWindowTitle("Duplicate File Test")
        self.resize(600, 200)
        
        layout = QVBoxLayout(self)
        
        # Create DatabaseManager and FolderManager
        self.db_manager = DatabaseManager()
        
        folder_manager = FolderManager()
        folder_manager.attach_db_manager(self.db_manager)
        
        # Create test buttons
        self.add_button = QPushButton("Add Test Recording")
        self.add_button.clicked.connect(self.add_test_recording)
        layout.addWidget(self.add_button)
        
        self.add_duplicate_button = QPushButton("Add Duplicate Recording (Should Show Error)")
        self.add_duplicate_button.clicked.connect(self.add_duplicate_recording)
        layout.addWidget(self.add_duplicate_button)
        
        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)
        
    def add_test_recording(self):
        """Add a test recording to the database"""
        self.status_label.setText("Adding test recording...")
        
        # Prepare test recording data
        import datetime
        filename = "test_recording.mp3"
        file_path = "/tmp/test_recording.mp3"
        date_created = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        duration = 60  # 1 minute
        original_source = file_path
        
        # Create recording in database
        recording_data = (filename, file_path, date_created, duration, "", "", original_source)
        
        # Define callback for when the recording is created
        def on_recording_created(recording_id):
            self.status_label.setText(f"Added test recording with ID: {recording_id}")
            logger.info(f"Recording created with ID: {recording_id}")
        
        # Connect to handle database errors (similar to MainWindow.on_new_file)
        def on_db_error(operation_name, error_message):
            if operation_name == "create_recording":
                error_text = f"DB error while adding '{filename}': {error_message}"
                logger.error(f"Database error: {error_text}")
                self.status_label.setText(error_text)
                
                # Disconnect after first delivery
                try:
                    self.db_manager.error_occurred.disconnect(on_db_error)
                except TypeError:
                    pass
        
        # Connect with UniqueConnection
        self.db_manager.error_occurred.connect(on_db_error, Qt.ConnectionType.UniqueConnection)
        
        # Create the recording
        self.db_manager.create_recording(recording_data, on_recording_created)
        
        # Set a timeout to disconnect the error handler if no error occurs
        def disconnect_error_handler():
            try:
                self.db_manager.error_occurred.disconnect(on_db_error)
                logger.debug(f"Disconnected error handler for {filename}")
            except TypeError:
                pass
        
        # Disconnect after 2 seconds if no error occurred
        QTimer.singleShot(2000, disconnect_error_handler)
    
    def add_duplicate_recording(self):
        """Try to add a recording with the same file path (should trigger the error)"""
        self.status_label.setText("Adding duplicate recording (should fail)...")
        
        # Use the same path as the test recording
        import datetime
        filename = "duplicate_recording.mp3"  # Different name but same path
        file_path = "/tmp/test_recording.mp3"  # Same path as the first recording
        date_created = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        duration = 120  # Different duration
        original_source = file_path
        
        # Create recording in database
        recording_data = (filename, file_path, date_created, duration, "", "", original_source)
        
        # Define callback for when the recording is created (should not be called)
        def on_recording_created(recording_id):
            self.status_label.setText(f"UNEXPECTED SUCCESS: Added duplicate recording with ID: {recording_id}")
            logger.warning(f"Duplicate recording created with ID: {recording_id} - this should not happen!")
        
        # Connect to handle database errors
        def on_db_error(operation_name, error_message):
            if operation_name == "create_recording":
                error_text = f"DB error while adding '{filename}': {error_message}"
                logger.error(f"Database error: {error_text}")
                self.status_label.setText(error_text)
                
                # Disconnect after first delivery
                try:
                    self.db_manager.error_occurred.disconnect(on_db_error)
                except TypeError:
                    pass
        
        # Connect with UniqueConnection
        self.db_manager.error_occurred.connect(on_db_error, Qt.ConnectionType.UniqueConnection)
        
        # Try to create the duplicate recording
        self.db_manager.create_recording(recording_data, on_recording_created)
        
        # Set a timeout to disconnect the error handler if no error occurs
        def disconnect_error_handler():
            try:
                self.db_manager.error_occurred.disconnect(on_db_error)
                logger.debug(f"Disconnected error handler for {filename}")
            except TypeError:
                pass
        
        # Disconnect after 2 seconds if no error occurred
        QTimer.singleShot(2000, disconnect_error_handler)

def main():
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())