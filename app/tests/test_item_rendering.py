#!/usr/bin/env python
"""
Test to verify proper rendering of recording items without text overlap.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

# Add parent directory to path for imports
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

class TestItemRendering(unittest.TestCase):
    """Test case for verifying proper rendering of items without text overlap."""
    
    @classmethod
    def setUpClass(cls):
        """Set up the QApplication for all tests."""
        cls.app = QApplication.instance() or QApplication(sys.argv)
    
    def setUp(self):
        """Set up test environment."""
        # Mock database manager and folder manager
        self.db_manager = MagicMock()
        
        # Create patches
        self.patches = [
            patch('app.RecentRecordingsWidget.FolderManager'),
            patch('app.RecentRecordingsWidget.DatabaseManager')
        ]
        
        # Start patches
        self.mocks = [p.start() for p in self.patches]
        self.mock_folder_manager = self.mocks[0].instance.return_value
        self.mock_db_manager = self.mocks[1].instance.return_value
        
        # Create mock data
        self.mock_folder_manager.get_all_root_folders.return_value = [
            {'id': 1, 'name': 'Test Folder', 'children': []}
        ]
        
        # Mock empty recordings lists
        self.mock_folder_manager.get_recordings_in_folder.return_value = []
        self.mock_folder_manager.get_recordings_not_in_folders.return_value = []
        
    def tearDown(self):
        """Clean up after tests."""
        # Stop all patches
        for p in self.patches:
            p.stop()
    
    # Test removed as UnifiedFolderListWidget is obsolete, replaced by UnifiedFolderTreeView
    # The _add_recording_item method is now part of the model/view architecture
    # and text overlap is now handled by the RecordingItemDelegate in UnifiedFolderTreeView
    @patch('app.RecordingListItem.RecordingListItem')
    def test_treewidget_item_has_empty_text(self, mock_recording_item_class):
        """Test that tree items have empty text to avoid overlap (using UnifiedFolderTreeView)."""
        from app.UnifiedFolderTreeView import UnifiedFolderTreeView
        
        # Test is now handled by test_delegate_clears_text_in_paint
        self.skipTest("UnifiedFolderListWidget has been removed; this functionality is now tested by test_delegate_clears_text_in_paint")
    
    @patch('app.RecordingFolderModel.QStandardItem')
    def test_model_item_has_empty_text(self, mock_standard_item_class):
        """Test that model items have empty text to avoid overlap."""
        from app.RecordingFolderModel import RecordingFolderModel
        
        # Create mock standard item
        mock_standard_item = MagicMock()
        mock_standard_item_class.return_value = mock_standard_item
        
        # Create the model
        model = RecordingFolderModel()
        
        # Set required icons
        model.audio_icon = MagicMock()
        model.video_icon = MagicMock()
        model.file_icon = MagicMock()
        
        # Create a mock recording data and parent item
        recording_data = [1, "Test Recording.mp3", "/path/to/recording.mp3", 
                         "2023-01-01 12:00:00", "", "", ""]
        parent_item = MagicMock()
        
        # Add the recording to the model
        model.add_recording_item(recording_data, parent_item)
        
        # Verify setText was called with empty string
        mock_standard_item.setText.assert_called_with("")
        
    def test_delegate_clears_text_in_paint(self):
        """Test that the delegate clears text during painting for recordings."""
        from app.UnifiedFolderTreeView import RecordingItemDelegate
        from app.RecordingFolderModel import RecordingFolderModel
        
        # Create a mock StyleOptionView and painter
        option = MagicMock()
        painter = MagicMock()
        index = MagicMock()
        
        # Configure mock index to return recording type
        index.data.return_value = "recording"
        
        # Create delegate and call paint
        delegate = RecordingItemDelegate()
        
        # Patch the superclass paint method
        with patch.object(delegate.__class__.__mro__[1], 'paint') as mock_super_paint:
            delegate.paint(painter, option, index)
            
            # Verify that the text in the option passed to super().paint was cleared
            mock_super_paint.assert_called_once()
            option_arg = mock_super_paint.call_args[0][1]
            self.assertEqual(option_arg.text, "")


if __name__ == '__main__':
    unittest.main()