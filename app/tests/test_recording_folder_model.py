"""
Unit tests for RecordingFolderModel and RecordingFilterProxyModel.
"""

import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from PyQt6.QtCore import Qt, QModelIndex
from PyQt6.QtGui import QStandardItem, QIcon
from PyQt6.QtWidgets import QApplication

# Import the modules to be tested
from app.RecordingFolderModel import RecordingFolderModel, RecordingFilterProxyModel

class TestRecordingFolderModel(unittest.TestCase):
    """Test suite for the RecordingFolderModel class."""
    
    @classmethod
    def setUpClass(cls):
        """Set up the test environment once for all tests."""
        # Create a QApplication instance if not already created
        cls.app = QApplication(sys.argv) if not QApplication.instance() else QApplication.instance()
    
    def setUp(self):
        """Set up before each test."""
        # Create a RecordingFolderModel instance
        self.model = RecordingFolderModel()
        
        # Create mock icons
        self.mock_folder_icon = QIcon()
        self.mock_folder_open_icon = QIcon()
        self.mock_audio_icon = QIcon()
        self.mock_video_icon = QIcon()
        self.mock_file_icon = QIcon()
        
        # Set mock icons
        self.model.set_icons(
            self.mock_folder_icon,
            self.mock_folder_open_icon,
            self.mock_audio_icon,
            self.mock_video_icon,
            self.mock_file_icon
        )
    
    def test_add_folder_item_sets_roles(self):
        """Test that add_folder_item sets the correct roles."""
        # Create a mock folder data
        folder_data = {
            'id': 1,
            'name': 'Test Folder',
            'parent_id': None,
            'created_at': '2025-01-01 12:00:00',
            'children': []
        }
        
        # Add folder to model
        folder_item = self.model.add_folder_item(folder_data)
        
        # Verify roles are set correctly
        self.assertEqual(folder_item.text(), 'Test Folder', "Folder name should be set")
        self.assertEqual(folder_item.data(RecordingFolderModel.ITEM_TYPE_ROLE), "folder", 
                       "Item type role should be 'folder'")
        self.assertEqual(folder_item.data(RecordingFolderModel.ITEM_ID_ROLE), 1, 
                       "Item ID role should be set to folder ID")
        
        # Verify folder is added to item_map
        self.assertIn(("folder", 1), self.model.item_map, "Folder should be added to item_map")
        self.assertIs(self.model.item_map[("folder", 1)], folder_item, 
                    "item_map should contain the folder item")
        
        # Verify folder is added to model
        self.assertEqual(self.model.rowCount(), 1, "Model should have 1 row")
        self.assertEqual(self.model.item(0, 0), folder_item, "First item in model should be the folder")
    
    def test_add_folder_item_with_parent(self):
        """Test adding a folder item with a parent folder."""
        # Create parent folder
        parent_folder_data = {
            'id': 1,
            'name': 'Parent Folder',
            'parent_id': None,
            'created_at': '2025-01-01 12:00:00',
            'children': []
        }
        parent_item = self.model.add_folder_item(parent_folder_data)
        
        # Create child folder
        child_folder_data = {
            'id': 2,
            'name': 'Child Folder',
            'parent_id': 1,
            'created_at': '2025-01-01 12:01:00',
            'children': []
        }
        child_item = self.model.add_folder_item(child_folder_data, parent_item)
        
        # Verify child folder is added to parent
        self.assertEqual(parent_item.rowCount(), 1, "Parent folder should have 1 child")
        self.assertEqual(parent_item.child(0, 0), child_item, "First child should be the child folder")
        
        # Verify child folder is added to item_map
        self.assertIn(("folder", 2), self.model.item_map, "Child folder should be added to item_map")
    
    def test_add_recording_item_sets_roles(self):
        """Test that add_recording_item sets the correct roles."""
        # Create a parent folder for the recording
        folder_data = {
            'id': 1,
            'name': 'Test Folder',
            'parent_id': None,
            'created_at': '2025-01-01 12:00:00',
            'children': []
        }
        folder_item = self.model.add_folder_item(folder_data)
        
        # Create a mock recording data
        # Format: (id, filename, file_path, date_created, raw_transcript, processed_text, ...)
        recording_data = (
            1,  # id
            "test_recording.mp3",  # filename
            "/path/to/test_recording.mp3",  # file_path
            "2025-01-01 12:00:00",  # date_created
            "This is a raw transcript",  # raw_transcript
            "This is processed text",  # processed_text
            None,  # raw_transcript_formatted
            None   # processed_text_formatted
        )
        
        # Add recording to model
        recording_item = self.model.add_recording_item(recording_data, folder_item)
        
        # Verify roles are set correctly
        self.assertEqual(recording_item.text(), "", "Recording item should have empty text")
        self.assertEqual(recording_item.data(RecordingFolderModel.ITEM_TYPE_ROLE), "recording", 
                       "Item type role should be 'recording'")
        self.assertEqual(recording_item.data(RecordingFolderModel.ITEM_ID_ROLE), 1, 
                       "Item ID role should be set to recording ID")
        self.assertEqual(recording_item.data(RecordingFolderModel.FILE_PATH_ROLE), 
                       "/path/to/test_recording.mp3", "File path role should be set")
        
        # Verify transcript data is set
        expected_full_text = "test_recording.mp3 This is a raw transcript This is processed text"
        self.assertEqual(recording_item.data(RecordingFolderModel.FULL_TRANSCRIPT_ROLE), 
                       expected_full_text, "Full transcript role should be set")
        self.assertTrue(recording_item.data(RecordingFolderModel.HAS_TRANSCRIPT_ROLE), 
                      "HAS_TRANSCRIPT_ROLE should be True")
        
        # Verify date is parsed correctly
        date_created = recording_item.data(RecordingFolderModel.DATE_CREATED_ROLE)
        self.assertIsInstance(date_created, datetime, "DATE_CREATED_ROLE should be a datetime object")
        self.assertEqual(date_created.year, 2025, "Year should be parsed correctly")
        self.assertEqual(date_created.month, 1, "Month should be parsed correctly")
        self.assertEqual(date_created.day, 1, "Day should be parsed correctly")
        
        # Verify recording is added to item_map
        self.assertIn(("recording", 1), self.model.item_map, "Recording should be added to item_map")
        
        # Verify recording is added to folder
        self.assertEqual(folder_item.rowCount(), 1, "Folder should have 1 child")
        self.assertEqual(folder_item.child(0, 0), recording_item, 
                       "First child should be the recording")
    
    def test_add_recording_item_with_null_transcript(self):
        """Test adding a recording with null transcript values."""
        # Create a parent folder for the recording
        folder_data = {
            'id': 1,
            'name': 'Test Folder',
            'parent_id': None,
            'created_at': '2025-01-01 12:00:00',
            'children': []
        }
        folder_item = self.model.add_folder_item(folder_data)
        
        # Create a mock recording data with null transcripts
        recording_data = (
            1,  # id
            "test_recording.mp3",  # filename
            "/path/to/test_recording.mp3",  # file_path
            "2025-01-01 12:00:00",  # date_created
            None,  # raw_transcript
            None,  # processed_text
            None,  # raw_transcript_formatted
            None   # processed_text_formatted
        )
        
        # Add recording to model
        recording_item = self.model.add_recording_item(recording_data, folder_item)
        
        # Verify transcript data is handled properly
        expected_full_text = "test_recording.mp3  "  # Two spaces from concat of None -> ""
        self.assertEqual(recording_item.data(RecordingFolderModel.FULL_TRANSCRIPT_ROLE), 
                       expected_full_text, "Full transcript role should be set with empty strings")
        self.assertFalse(recording_item.data(RecordingFolderModel.HAS_TRANSCRIPT_ROLE), 
                       "HAS_TRANSCRIPT_ROLE should be False")
    
    def test_determine_file_type(self):
        """Test determining file type from extension."""
        # Test audio file
        self.assertEqual(self.model._determine_file_type("/path/to/file.mp3"), "audio", 
                       "MP3 file should be detected as audio")
        self.assertEqual(self.model._determine_file_type("/path/to/file.wav"), "audio", 
                       "WAV file should be detected as audio")
        self.assertEqual(self.model._determine_file_type("/path/to/file.m4a"), "audio", 
                       "M4A file should be detected as audio")
        
        # Test video file
        self.assertEqual(self.model._determine_file_type("/path/to/file.mp4"), "video", 
                       "MP4 file should be detected as video")
        self.assertEqual(self.model._determine_file_type("/path/to/file.mov"), "video", 
                       "MOV file should be detected as video")
        
        # Test unknown file
        self.assertEqual(self.model._determine_file_type("/path/to/file.txt"), "unknown", 
                       "TXT file should be detected as unknown")
        self.assertEqual(self.model._determine_file_type("/path/to/file"), "unknown", 
                       "File without extension should be detected as unknown")
        self.assertEqual(self.model._determine_file_type(None), "unknown", 
                       "None path should be detected as unknown")
    
    def test_get_item_by_id(self):
        """Test retrieving items by ID and type."""
        # Add a folder and recording
        folder_data = {
            'id': 1,
            'name': 'Test Folder',
            'parent_id': None,
            'created_at': '2025-01-01 12:00:00',
            'children': []
        }
        folder_item = self.model.add_folder_item(folder_data)
        
        recording_data = (
            2,  # id
            "test_recording.mp3",  # filename
            "/path/to/test_recording.mp3",  # file_path
            "2025-01-01 12:00:00",  # date_created
            "transcript",  # raw_transcript
            "processed",  # processed_text
            None,  # raw_transcript_formatted
            None   # processed_text_formatted
        )
        recording_item = self.model.add_recording_item(recording_data, folder_item)
        
        # Retrieve items by ID
        retrieved_folder = self.model.get_item_by_id(1, "folder")
        retrieved_recording = self.model.get_item_by_id(2, "recording")
        
        # Verify retrieved items
        self.assertIs(retrieved_folder, folder_item, "Retrieved folder should be the same object")
        self.assertIs(retrieved_recording, recording_item, "Retrieved recording should be the same object")
        
        # Test retrieving non-existent item
        self.assertIsNone(self.model.get_item_by_id(999, "folder"), 
                         "Non-existent folder should return None")
    
    def test_clear_model(self):
        """Test clearing the model."""
        # Add a folder and recording
        folder_data = {
            'id': 1,
            'name': 'Test Folder',
            'parent_id': None,
            'created_at': '2025-01-01 12:00:00',
            'children': []
        }
        self.model.add_folder_item(folder_data)
        
        # Verify model has items
        self.assertEqual(self.model.rowCount(), 1, "Model should have 1 row")
        self.assertIn(("folder", 1), self.model.item_map, "Folder should be in item_map")
        
        # Clear model
        self.model.clear_model()
        
        # Verify model is empty
        self.assertEqual(self.model.rowCount(), 0, "Model should have 0 rows after clearing")
        self.assertEqual(len(self.model.item_map), 0, "item_map should be empty after clearing")


class TestRecordingFilterProxyModel(unittest.TestCase):
    """Test suite for the RecordingFilterProxyModel class."""
    
    @classmethod
    def setUpClass(cls):
        """Set up the test environment once for all tests."""
        # Create a QApplication instance if not already created
        cls.app = QApplication(sys.argv) if not QApplication.instance() else QApplication.instance()
    
    def setUp(self):
        """Set up before each test."""
        # Create a source model and populate it
        self.source_model = RecordingFolderModel()
        
        # Create mock icons
        mock_folder_icon = QIcon()
        mock_folder_open_icon = QIcon()
        mock_audio_icon = QIcon()
        mock_video_icon = QIcon()
        mock_file_icon = QIcon()
        
        # Set mock icons
        self.source_model.set_icons(
            mock_folder_icon,
            mock_folder_open_icon,
            mock_audio_icon,
            mock_video_icon,
            mock_file_icon
        )
        
        # Add a root folder
        root_folder_data = {
            'id': 1,
            'name': 'Audio Files',
            'parent_id': None,
            'created_at': '2025-01-01 12:00:00',
            'children': []
        }
        self.root_folder = self.source_model.add_folder_item(root_folder_data)
        
        # Add a subfolder
        sub_folder_data = {
            'id': 2,
            'name': 'Podcasts',
            'parent_id': 1,
            'created_at': '2025-01-01 12:01:00',
            'children': []
        }
        self.sub_folder = self.source_model.add_folder_item(sub_folder_data, self.root_folder)
        
        # Add recordings to root folder
        # Recording with transcript
        self.recording1_data = (
            1,  # id
            "interview.mp3",  # filename
            "/path/to/interview.mp3",  # file_path
            "2025-01-01 12:00:00",  # date_created
            "This is an interview transcript",  # raw_transcript
            "This is processed interview text",  # processed_text
            None,  # raw_transcript_formatted
            None   # processed_text_formatted
        )
        self.recording1 = self.source_model.add_recording_item(self.recording1_data, self.root_folder)
        
        # Recording without transcript
        self.recording2_data = (
            2,  # id
            "music.mp3",  # filename
            "/path/to/music.mp3",  # file_path
            "2025-01-01 12:00:00",  # date_created
            None,  # raw_transcript
            None,  # processed_text
            None,  # raw_transcript_formatted
            None   # processed_text_formatted
        )
        self.recording2 = self.source_model.add_recording_item(self.recording2_data, self.root_folder)
        
        # Add recordings to subfolder
        # Recent recording with transcript
        now = datetime.now()
        recent_date = now.strftime("%Y-%m-%d %H:%M:%S")
        self.recording3_data = (
            3,  # id
            "podcast.mp3",  # filename
            "/path/to/podcast.mp3",  # file_path
            recent_date,  # date_created (recent)
            "This is a podcast transcript",  # raw_transcript
            "This is processed podcast text",  # processed_text
            None,  # raw_transcript_formatted
            None   # processed_text_formatted
        )
        self.recording3 = self.source_model.add_recording_item(self.recording3_data, self.sub_folder)
        
        # Create the proxy model
        self.proxy_model = RecordingFilterProxyModel()
        self.proxy_model.setSourceModel(self.source_model)
    
    def test_filter_text_match_name(self):
        """Test filtering by text matching filename."""
        # Set filter text
        self.proxy_model.setFilterText("interview")
        
        # Get root folder index in proxy model
        root_index = self.proxy_model.mapFromSource(self.source_model.indexFromItem(self.root_folder))
        
        # Verify root folder is visible (contains a matching child)
        self.assertTrue(root_index.isValid(), "Root folder should be visible")
        
        # Verify matching recording is visible
        recording1_index = self.proxy_model.mapFromSource(self.source_model.indexFromItem(self.recording1))
        self.assertTrue(recording1_index.isValid(), "Recording with matching name should be visible")
        
        # Verify non-matching recording is hidden
        recording2_index = self.proxy_model.mapFromSource(self.source_model.indexFromItem(self.recording2))
        self.assertFalse(recording2_index.isValid(), "Recording with non-matching name should be hidden")
    
    def test_filter_text_match_transcript(self):
        """Test filtering by text matching transcript."""
        # Set filter text
        self.proxy_model.setFilterText("podcast")
        
        # Verify subfolder is visible (contains a matching child)
        subfolder_index = self.proxy_model.mapFromSource(self.source_model.indexFromItem(self.sub_folder))
        self.assertTrue(subfolder_index.isValid(), "Subfolder should be visible")
        
        # Verify matching recording is visible
        recording3_index = self.proxy_model.mapFromSource(self.source_model.indexFromItem(self.recording3))
        self.assertTrue(recording3_index.isValid(), "Recording with matching transcript should be visible")
    
    def test_filter_text_no_match(self):
        """Test filtering with no matches."""
        # Set filter text
        self.proxy_model.setFilterText("nonexistent")
        
        # Verify model is empty (no matching items)
        self.assertEqual(self.proxy_model.rowCount(), 0, "Model should have no rows")
    
    def test_filter_criteria_all(self):
        """Test filter criteria 'All'."""
        # Set filter criteria
        self.proxy_model.setFilterCriteria("All")
        
        # Verify all recordings are visible
        root_index = self.proxy_model.mapFromSource(self.source_model.indexFromItem(self.root_folder))
        self.assertTrue(root_index.isValid(), "Root folder should be visible")
        
        recording1_index = self.proxy_model.mapFromSource(self.source_model.indexFromItem(self.recording1))
        self.assertTrue(recording1_index.isValid(), "Recording1 should be visible")
        
        recording2_index = self.proxy_model.mapFromSource(self.source_model.indexFromItem(self.recording2))
        self.assertTrue(recording2_index.isValid(), "Recording2 should be visible")
    
    def test_filter_criteria_has_transcript(self):
        """Test filter criteria 'Has Transcript'."""
        # Set filter criteria
        self.proxy_model.setFilterCriteria("Has Transcript")
        
        # Verify recordings with transcript are visible
        recording1_index = self.proxy_model.mapFromSource(self.source_model.indexFromItem(self.recording1))
        self.assertTrue(recording1_index.isValid(), "Recording with transcript should be visible")
        
        # Verify recordings without transcript are hidden
        recording2_index = self.proxy_model.mapFromSource(self.source_model.indexFromItem(self.recording2))
        self.assertFalse(recording2_index.isValid(), "Recording without transcript should be hidden")
    
    def test_filter_criteria_no_transcript(self):
        """Test filter criteria 'No Transcript'."""
        # Set filter criteria
        self.proxy_model.setFilterCriteria("No Transcript")
        
        # Verify recordings without transcript are visible
        recording2_index = self.proxy_model.mapFromSource(self.source_model.indexFromItem(self.recording2))
        self.assertTrue(recording2_index.isValid(), "Recording without transcript should be visible")
        
        # Verify recordings with transcript are hidden
        recording1_index = self.proxy_model.mapFromSource(self.source_model.indexFromItem(self.recording1))
        self.assertFalse(recording1_index.isValid(), "Recording with transcript should be hidden")
    
    def test_filter_criteria_recent(self):
        """Test filter criteria 'Recent (24h)'."""
        # Set filter criteria
        self.proxy_model.setFilterCriteria("Recent (24h)")
        
        # Verify recent recordings are visible
        recording3_index = self.proxy_model.mapFromSource(self.source_model.indexFromItem(self.recording3))
        self.assertTrue(recording3_index.isValid(), "Recent recording should be visible")
        
        # Verify old recordings are hidden
        recording1_index = self.proxy_model.mapFromSource(self.source_model.indexFromItem(self.recording1))
        self.assertFalse(recording1_index.isValid(), "Old recording should be hidden")
    
    def test_filter_accepts_folder_if_child_matches(self):
        """Test that folders are visible if they contain matching children."""
        # Set filter text to match a recording in the subfolder
        self.proxy_model.setFilterText("podcast")
        
        # Verify subfolder is visible (contains a matching recording)
        subfolder_index = self.proxy_model.mapFromSource(self.source_model.indexFromItem(self.sub_folder))
        self.assertTrue(subfolder_index.isValid(), "Subfolder should be visible")
        
        # Verify root folder is visible (contains a visible subfolder)
        root_index = self.proxy_model.mapFromSource(self.source_model.indexFromItem(self.root_folder))
        self.assertTrue(root_index.isValid(), "Root folder should be visible")
    
    def test_filter_rejects_folder_if_no_child_matches(self):
        """Test that folders are hidden if no children match."""
        # Create a new empty folder
        empty_folder_data = {
            'id': 3,
            'name': 'Empty Folder',
            'parent_id': None,
            'created_at': '2025-01-01 12:00:00',
            'children': []
        }
        empty_folder = self.source_model.add_folder_item(empty_folder_data)
        
        # Set filter text to match a recording in the root folder
        self.proxy_model.setFilterText("interview")
        
        # Verify empty folder is hidden (no matching children)
        empty_folder_index = self.proxy_model.mapFromSource(self.source_model.indexFromItem(empty_folder))
        self.assertFalse(empty_folder_index.isValid(), "Empty folder should be hidden")
    
    def test_filter_handles_null_transcript(self):
        """Test handling NULL or empty transcript values in filter."""
        # Set filter text to match recording name but not transcript (which is NULL)
        self.proxy_model.setFilterText("music")
        
        # Verify recording with NULL transcript but matching name is visible
        recording2_index = self.proxy_model.mapFromSource(self.source_model.indexFromItem(self.recording2))
        self.assertTrue(recording2_index.isValid(), 
                      "Recording with NULL transcript but matching name should be visible")


if __name__ == '__main__':
    unittest.main()