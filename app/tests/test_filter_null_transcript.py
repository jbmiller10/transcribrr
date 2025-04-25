import unittest
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import QModelIndex
from PyQt6.QtGui import QStandardItem

from app.RecordingFolderModel import RecordingFolderModel, RecordingFilterProxyModel


class TestFilterNullTranscript(unittest.TestCase):
    """Test that filter proxy handles NULL transcript fields correctly."""

    def setUp(self):
        """Set up test models."""
        # Create a source model
        self.source_model = RecordingFolderModel()
        
        # Create a filter proxy model
        self.filter_proxy = RecordingFilterProxyModel()
        self.filter_proxy.setSourceModel(self.source_model)

    def test_filter_with_null_transcript(self):
        """Test that filtering with NULL transcript fields doesn't cause AttributeError."""
        # Create a recording item with NULL transcript
        item = QStandardItem()
        item.setData("recording", RecordingFolderModel.ITEM_TYPE_ROLE)
        item.setData(1, RecordingFolderModel.ITEM_ID_ROLE)
        item.setData(None, RecordingFolderModel.FULL_TRANSCRIPT_ROLE)  # NULL transcript
        
        # Add to source model
        self.source_model.appendRow(item)
        
        # Mock the source model's itemFromIndex method to return our item
        def mock_item_from_index(index):
            return item
        
        self.source_model.itemFromIndex = mock_item_from_index
        
        # Set filter text
        self.filter_proxy.setFilterText("test")
        
        # This should not raise AttributeError
        try:
            # Create a mock index
            mock_index = MagicMock(spec=QModelIndex)
            mock_index.isValid.return_value = True
            
            # Call filterAcceptsRow directly
            result = self.filter_proxy.filterAcceptsRow(0, QModelIndex())
            
            # We expect it to return False since the item doesn't match the filter
            self.assertFalse(result)
        except AttributeError:
            self.fail("filterAcceptsRow raised AttributeError with NULL transcript")

    def test_filter_accepts_valid_transcript(self):
        """Test that filtering works with valid transcript."""
        # Create a recording item with a valid transcript
        item = QStandardItem()
        item.setData("recording", RecordingFolderModel.ITEM_TYPE_ROLE)
        item.setData(1, RecordingFolderModel.ITEM_ID_ROLE)
        item.setData("This is a test transcript", RecordingFolderModel.FULL_TRANSCRIPT_ROLE)
        
        # Add to source model
        self.source_model.appendRow(item)
        
        # Mock the source model's itemFromIndex method to return our item
        def mock_item_from_index(index):
            return item
        
        self.source_model.itemFromIndex = mock_item_from_index
        
        # Set filter text
        self.filter_proxy.setFilterText("test")
        
        # Call filterAcceptsRow
        result = self.filter_proxy.filterAcceptsRow(0, QModelIndex())
        
        # We expect it to return True since the item matches the filter
        self.assertTrue(result)


if __name__ == '__main__':
    unittest.main()