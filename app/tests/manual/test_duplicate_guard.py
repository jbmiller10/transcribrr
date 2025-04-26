#!/usr/bin/env python3
"""
Manual test to verify that duplicate file path errors are properly handled and
no phantom refreshes are triggered in the UI.
"""

import sys
import time
import logging
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from app.DatabaseManager import DatabaseManager
from app.FolderManager import FolderManager

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TestWindow(QWidget):
    def __init__(self):
        super().__init__()
        
        # Set up UI
        self.setWindowTitle("Duplicate Path Guard Test")
        self.resize(800, 500)
        
        layout = QVBoxLayout(self)
        
        # Create DatabaseManager and FolderManager
        self.db_manager = DatabaseManager()
        
        # Track dataChanged signals for testing
        self.data_changed_count = 0
        self.db_manager.dataChanged.connect(self.on_data_changed)
        
        folder_manager = FolderManager()
        folder_manager.attach_db_manager(self.db_manager)
        
        # Add buttons
        self.add_button = QPushButton("Add Test Recording")
        self.add_button.clicked.connect(self.add_test_recording)
        layout.addWidget(self.add_button)
        
        self.add_duplicate_button = QPushButton("Add Duplicate Recording (Should Handle Gracefully)")
        self.add_duplicate_button.clicked.connect(self.add_duplicate_recording)
        layout.addWidget(self.add_duplicate_button)
        
        # Status information
        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)
        
        self.data_changed_label = QLabel("Data changed count: 0")
        layout.addWidget(self.data_changed_label)
        
        self.error_label = QLabel("")
        layout.addWidget(self.error_label)
        
        # Logs
        self.log_label = QLabel("Event Log:")
        layout.addWidget(self.log_label)
        
        self.log_area = QLabel("")
        self.log_area.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.log_area.setWordWrap(True)
        self.log_area.setStyleSheet("background-color: #f0f0f0; padding: 10px; border-radius: 5px;")
        self.log_area.setMinimumHeight(200)
        layout.addWidget(self.log_area)
        
    def on_data_changed(self, entity_type=None, entity_id=None):
        """Track dataChanged signals"""
        self.data_changed_count += 1
        self.data_changed_label.setText(f"Data changed count: {self.data_changed_count}")
        self.add_log(f"DATA CHANGED signal received - type: {entity_type}, id: {entity_id}")
        
    def add_log(self, message):
        """Add message to log area"""
        current_text = self.log_area.text()
        # Add timestamp
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        new_entry = f"[{timestamp}] {message}"
        
        # Update log area (limit to last 10 entries for readability)
        if current_text:
            log_lines = current_text.split('\n')
            log_lines.append(new_entry)
            if len(log_lines) > 10:
                log_lines = log_lines[-10:]  # Keep only last 10 lines
            self.log_area.setText('\n'.join(log_lines))
        else:
            self.log_area.setText(new_entry)
            
    def add_test_recording(self):
        """Add a test recording to the database"""
        self.status_label.setText("Adding test recording...")
        self.add_log("Adding test recording...")
        
        # Prepare test recording data
        import datetime
        filename = "test_recording.mp3"
        file_path = "/tmp/test_recording_guard.mp3"  # Use a unique path for this test
        date_created = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        duration = 60  # 1 minute
        original_source = file_path
        
        # Create recording in database
        recording_data = (filename, file_path, date_created, duration, "", "", original_source)
        
        # Define callback for when the recording is created
        def on_recording_created(recording_id):
            self.status_label.setText(f"Added test recording with ID: {recording_id}")
            self.add_log(f"Recording created with ID: {recording_id}")
        
        # Connect to handle database errors
        def on_db_error(operation_name, error_message):
            if operation_name == "create_recording":
                error_text = f"DB error while adding '{filename}': {error_message}"
                logger.error(f"Database error: {error_text}")
                self.error_label.setText(error_text)
                self.add_log(f"ERROR: {error_text}")
                
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
        self.status_label.setText("Adding duplicate recording (should fail gracefully)...")
        self.add_log("Attempting to add duplicate recording (should fail gracefully)...")
        
        # Record current data changed count to verify it doesn't increase for duplicate path
        initial_count = self.data_changed_count
        
        # Use the same path as the test recording
        import datetime
        filename = "duplicate_recording.mp3"  # Different name but same path
        file_path = "/tmp/test_recording_guard.mp3"  # Same path as the first recording
        date_created = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        duration = 120  # Different duration
        original_source = file_path
        
        # Create recording in database
        recording_data = (filename, file_path, date_created, duration, "", "", original_source)
        
        # Define callback for when the recording is created (should not be called)
        def on_recording_created(recording_id):
            self.status_label.setText(f"UNEXPECTED SUCCESS: Added duplicate recording with ID: {recording_id}")
            self.add_log(f"UNEXPECTED: Duplicate recording created with ID: {recording_id} - BUG!")
            
            # Check if dataChanged count increased - should NOT happen
            if self.data_changed_count > initial_count:
                self.add_log("BUG: dataChanged signal was emitted for duplicate path!")
        
        # Connect to handle database errors
        def on_db_error(operation_name, error_message):
            if operation_name == "create_recording":
                error_text = f"DB error while adding '{filename}': {error_message}"
                logger.error(f"Database error: {error_text}")
                self.error_label.setText(error_text)
                self.add_log(f"Expected error received: {error_text}")
                
                # Verify dataChanged count didn't increase
                QTimer.singleShot(500, self.verify_no_phantom_refresh)
                
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
        
    def verify_no_phantom_refresh(self):
        """Verify that no phantom refresh occurred after duplicate path error"""
        initial_count = self.data_changed_count
        
        # Check after a brief delay to make sure all signals have been processed
        def check_data_changed_count():
            if self.data_changed_count > initial_count:
                self.add_log("BUG: dataChanged signal was emitted after duplicate path error!")
                self.error_label.setText("BUG: Phantom refresh occurred!")
            else:
                self.add_log("SUCCESS: No phantom refresh occurred")
                self.status_label.setText("Test passed: Error handled correctly, no phantom refresh")
        
        # Check after a short delay to allow any pending signals to be processed
        QTimer.singleShot(500, check_data_changed_count)

def main():
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())