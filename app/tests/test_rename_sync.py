"""Unit tests for the file rename synchronization feature."""

import os
import unittest
import tempfile
import sqlite3
import shutil
from unittest.mock import MagicMock, patch
import threading
import time

from app.db_utils import get_connection, create_recordings_table, create_recording, get_recording_by_id, update_recording
from app.RecentRecordingsWidget import RecentRecordingsWidget
from app.constants import FIELD_FILENAME, FIELD_FILE_PATH


class TestRenameSync(unittest.TestCase):
    """Tests for the rename synchronization between DB and filesystem."""
    
    def setUp(self):
        """Set up test environment."""
        # Create a temporary directory for test files
        self.test_dir = tempfile.mkdtemp()
        
        # Create a temporary database
        self.db_path = os.path.join(self.test_dir, "test_db.sqlite")
        self.conn = sqlite3.connect(self.db_path)
        create_recordings_table(self.conn)
        
        # Create a test file
        self.test_file_path = os.path.join(self.test_dir, "test_recording.mp3")
        with open(self.test_file_path, 'w') as f:
            f.write("test content")
        
        # Insert a test recording into the database
        self.recording_data = (
            "test_recording.mp3",  # filename
            self.test_file_path,   # file_path
            "2023-01-01 12:00:00", # date_created
            "00:01:00",            # duration
            None,                  # raw_transcript
            None                   # processed_text
        )
        self.recording_id = create_recording(self.conn, self.recording_data)
        
        # Mock dependencies for RecentRecordingsWidget
        self.mock_widget = MagicMock()
        self.mock_widget.get_filename.return_value = "test_recording.mp3"
        self.mock_widget.file_path = self.test_file_path
        self.mock_widget.filename_no_ext = "test_recording"
        
        self.mock_unified_view = MagicMock()
        self.mock_unified_view.recordings_map = {self.recording_id: self.mock_widget}
        
        # Create a patched RecentRecordingsWidget
        with patch('app.RecentRecordingsWidget.os.path.exists', return_value=True):
            self.widget = RecentRecordingsWidget(None)
            self.widget.unified_view = self.mock_unified_view
            self.widget.db_manager = MagicMock()
            self.widget.show_status_message = MagicMock()
    
    def tearDown(self):
        """Clean up test environment."""
        self.conn.close()
        shutil.rmtree(self.test_dir)
    
    def test_successful_rename(self):
        """Test successful rename operation syncs both DB and filesystem."""
        # Setup
        new_name = "renamed_recording"
        new_filename = "renamed_recording.mp3"
        new_path = os.path.join(self.test_dir, new_filename)
        
        # Create the on_rename_complete callback directly
        def simulate_db_update_callback():
            update_recording(self.conn, self.recording_id, filename=new_filename)
            
            # Mock the filesystem rename
            os.rename(self.test_file_path, new_path)
            
            # Mock the second DB update for file_path
            update_recording(self.conn, self.recording_id, file_path=new_path)
        
        # Patch os.rename to allow real rename to happen
        with patch('app.RecentRecordingsWidget.os.rename', side_effect=os.rename):
            # Execute - directly call the method with our mocked db_manager
            # This simulates most of the functionality without GUI dependencies
            self.widget.db_manager.update_recording = MagicMock(side_effect=simulate_db_update_callback)
            
            self.widget.handle_recording_rename(self.recording_id, new_name)
            
            # Verify both the database and file system were updated
            recording = get_recording_by_id(self.conn, self.recording_id)
            
            # Assertions
            self.assertEqual(recording[1], new_filename)  # Check DB filename updated
            self.assertEqual(recording[2], new_path)      # Check DB file_path updated
            self.assertTrue(os.path.exists(new_path))     # Check file exists at new path
            self.assertFalse(os.path.exists(self.test_file_path))  # Check old file is gone
    
    def test_rollback_on_filesystem_error(self):
        """Test that a filesystem error causes a DB rollback."""
        # Setup
        new_name = "renamed_recording"
        new_filename = "renamed_recording.mp3"
        
        # Capture original values for verification after rollback
        original_recording = get_recording_by_id(self.conn, self.recording_id)
        original_filename = original_recording[1]
        original_file_path = original_recording[2]
        
        # Track DB calls
        db_updates = []
        
        def simulate_db_update(recording_id, callback=None, **kwargs):
            db_updates.append(kwargs)
            
            # Simulate first update to filename
            if 'filename' in kwargs and not any('file_path' in d for d in db_updates):
                update_recording(self.conn, recording_id, filename=kwargs['filename'])
                
                # Call the callback to trigger the file rename operation
                if callback:
                    callback()
            
            # Simulate rollback update after file system error
            elif 'filename' in kwargs and any('file_path' in d for d in db_updates):
                # This is the rollback, reset the filename
                update_recording(self.conn, recording_id, filename=original_filename)
        
        # Mock dependencies
        self.widget.db_manager.update_recording = MagicMock(side_effect=simulate_db_update)
        
        # Create an error during file rename
        with patch('app.RecentRecordingsWidget.os.rename', side_effect=OSError("Permission denied")):
            # Execute
            self.widget.handle_recording_rename(self.recording_id, new_name)
            
            # Wait briefly for any async operations
            time.sleep(0.1)
            
            # Verify
            recording_after = get_recording_by_id(self.conn, self.recording_id)
            
            # Assertions - should be back to original state
            self.assertEqual(recording_after[1], original_filename)
            self.assertEqual(recording_after[2], original_file_path)
            self.assertTrue(os.path.exists(self.test_file_path))  # Original file still exists
    
    def test_prevents_overwriting_existing_file(self):
        """Test that rename prevents overwriting an existing file."""
        # Setup - create a file with the target name that already exists
        new_name = "existing_file"
        new_filename = "existing_file.mp3"
        existing_path = os.path.join(self.test_dir, new_filename)
        
        # Create the conflicting file
        with open(existing_path, 'w') as f:
            f.write("existing content")
        
        # Patch os.path.exists to return True for new path
        with patch('app.RecentRecordingsWidget.os.path.exists', 
                  side_effect=lambda path: path == existing_path or path == self.test_file_path):
            
            # Execute
            self.widget.handle_recording_rename(self.recording_id, new_name)
            
            # Verify
            recording_after = get_recording_by_id(self.conn, self.recording_id)
            
            # Assertions - should not have changed
            self.assertEqual(recording_after[1], "test_recording.mp3")
            self.assertEqual(recording_after[2], self.test_file_path)
            self.assertTrue(os.path.exists(self.test_file_path))  # Original file still exists
            self.assertTrue(os.path.exists(existing_path))       # Target file still exists
            
            # Check that error message was shown
            self.mock_widget.name_editable.setText.assert_called_with(self.mock_widget.filename_no_ext)


if __name__ == '__main__':
    unittest.main()