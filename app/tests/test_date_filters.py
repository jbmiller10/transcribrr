import sys
import os
import unittest
from datetime import datetime, timedelta
from PyQt6.QtCore import Qt, QModelIndex
from PyQt6.QtGui import QIcon

# Add the parent directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.RecordingFolderModel import RecordingFolderModel, RecordingFilterProxyModel

class TestDateFilters(unittest.TestCase):
    """Test date filtering in RecordingFilterProxyModel."""

    def setUp(self):
        """Set up the test."""
        self.source_model = RecordingFolderModel()
        self.proxy_model = RecordingFilterProxyModel()
        self.proxy_model.setSourceModel(self.source_model)
        
        # Create mock icons
        mock_icon = QIcon()
        self.source_model.set_icons(mock_icon, mock_icon, mock_icon, mock_icon, mock_icon)
        
        # Add a root folder
        self.root_folder = {"type": "folder", "id": -1, "name": "Test Root", "children": []}
        self.root_item = self.source_model.add_folder_item(self.root_folder)

    def test_this_week_filter(self):
        """Test 'This Week' filter with item from 3 days ago."""
        # Calculate a date 3 days ago
        today = datetime.now()
        three_days_ago = today - timedelta(days=3)
        date_str = three_days_ago.strftime("%Y-%m-%d %H:%M:%S")
        
        # Create test recording data with date 3 days ago
        recording_data = [
            1,                  # id
            "test_recording",   # filename
            "/path/to/test.mp3", # file_path
            date_str,           # date_created
            "test duration",    # duration
            "test transcript",  # raw_transcript
            "test processed",   # processed_text
            "test formatted",   # raw_transcript_formatted
            "test processed fmt" # processed_text_formatted
        ]
        
        # Add recording to model
        self.source_model.add_recording_item(recording_data, self.root_item)
        
        # Set filter to "This Week"
        self.proxy_model.setFilterCriteria("This Week")
        
        # Check that the recording is visible
        self.assertEqual(self.proxy_model.rowCount(), 1, "Root item should be visible")
        root_index = self.proxy_model.index(0, 0)
        self.assertEqual(self.proxy_model.rowCount(root_index), 1, 
                         "Recording from 3 days ago should be visible with 'This Week' filter")

    def test_recent_24h_filter(self):
        """Test 'Recent (24h)' filter with recent and old items."""
        # Create a recording from 2 days ago (should be filtered out)
        two_days_ago = datetime.now() - timedelta(days=2)
        old_date_str = two_days_ago.strftime("%Y-%m-%d %H:%M:%S")
        
        old_recording = [
            2,                  # id
            "old_recording",    # filename
            "/path/to/old.mp3", # file_path
            old_date_str,       # date_created
            "old duration",     # duration
            "old transcript",   # raw_transcript
            "old processed",    # processed_text
            "old formatted",    # raw_transcript_formatted
            "old processed fmt" # processed_text_formatted
        ]
        
        # Create a recording from 12 hours ago (should be visible)
        twelve_hours_ago = datetime.now() - timedelta(hours=12)
        recent_date_str = twelve_hours_ago.strftime("%Y-%m-%d %H:%M:%S")
        
        recent_recording = [
            3,                    # id
            "recent_recording",   # filename
            "/path/to/recent.mp3", # file_path
            recent_date_str,      # date_created
            "recent duration",    # duration
            "recent transcript",  # raw_transcript
            "recent processed",   # processed_text
            "recent formatted",   # raw_transcript_formatted
            "recent processed fmt" # processed_text_formatted
        ]
        
        # Add recordings to model
        self.source_model.add_recording_item(old_recording, self.root_item)
        self.source_model.add_recording_item(recent_recording, self.root_item)
        
        # Set filter to "Recent (24h)"
        self.proxy_model.setFilterCriteria("Recent (24h)")
        
        # Check that only the recent recording is visible
        self.assertEqual(self.proxy_model.rowCount(), 1, "Root item should be visible")
        root_index = self.proxy_model.index(0, 0)
        self.assertEqual(self.proxy_model.rowCount(root_index), 1, 
                         "Only the recording from 12 hours ago should be visible with 'Recent (24h)' filter")
        
        # Verify it's the right recording
        child_index = self.proxy_model.index(0, 0, root_index)
        source_index = self.proxy_model.mapToSource(child_index)
        item = self.source_model.itemFromIndex(source_index)
        item_id = item.data(RecordingFolderModel.ITEM_ID_ROLE)
        self.assertEqual(item_id, 3, "The visible recording should be the recent one with ID 3")


if __name__ == '__main__':
    unittest.main()