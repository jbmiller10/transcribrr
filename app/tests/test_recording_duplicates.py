import unittest
import logging
import os
import sys
import sqlite3
from unittest.mock import MagicMock, patch
from datetime import datetime

# Add parent directory to path for imports
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('test_duplicates')

# Mock PyQt6 dependencies
class MockQTreeWidgetItem:
    def __init__(self, parent=None):
        self.parent_item = parent
        self.children = []
        self.data_dict = {}
        self.expanded = False
        self.text_value = ""
        
        # Add as child to parent if provided
        if parent is not None:
            parent.children.append(self)
    
    def child(self, index):
        if 0 <= index < len(self.children):
            return self.children[index]
        return None
    
    def childCount(self):
        return len(self.children)
    
    def removeChild(self, child):
        if child in self.children:
            self.children.remove(child)
    
    def parent(self):
        return self.parent_item
    
    def data(self, column, role):
        return self.data_dict
    
    def setData(self, column, role, data):
        self.data_dict = data
    
    def setText(self, column, text):
        self.text_value = text
    
    def text(self, column):
        return self.text_value
    
    def setExpanded(self, expanded):
        self.expanded = expanded
    
    def isExpanded(self):
        return self.expanded
    
    def treeWidget(self):
        return self.tree_widget

class MockRecordingListItem:
    def __init__(self, rec_id, filename, file_path, date_created, duration="", 
                 raw_transcript="", processed_text="", raw_transcript_formatted=None,
                 processed_text_formatted=None, parent=None):
        self.id = rec_id
        self.filename = filename
        self.file_path = file_path
        self.date_created = date_created
        self.duration = duration
        self.raw_transcript = raw_transcript
        self.processed_text = processed_text
    
    def get_id(self):
        return self.id
    
    def refresh_folders(self):
        pass

class MockSignal:
    def __init__(self):
        self.connect = MagicMock()
        self.emit = MagicMock()

# Create mocked modules
sys.modules['PyQt6'] = MagicMock()
sys.modules['PyQt6.QtWidgets'] = MagicMock()
sys.modules['PyQt6.QtCore'] = MagicMock() 
sys.modules['PyQt6.QtGui'] = MagicMock()

# Import the module after mocking
with patch.dict('sys.modules', {
    'PyQt6': MagicMock(),
    'PyQt6.QtWidgets': MagicMock(),
    'PyQt6.QtCore': MagicMock(),
    'PyQt6.QtGui': MagicMock(),
}):
    # Add attributes to mocks
    sys.modules['PyQt6.QtCore'].pyqtSignal = lambda *args: MockSignal()
    sys.modules['PyQt6.QtCore'].Qt.ItemDataRole.UserRole = 1
    sys.modules['PyQt6.QtWidgets'].QTreeWidget = MagicMock
    sys.modules['PyQt6.QtWidgets'].QTreeWidgetItem = MockQTreeWidgetItem
    
    # Import the module to test
    from app.RecentRecordingsWidget import UnifiedFolderListWidget

class TestRecordingDuplicates(unittest.TestCase):
    """Test case for verifying no duplicate recordings in UnifiedFolderListWidget."""
    
    def setUp(self):
        """Set up mock objects and test environment."""
        # Create mock database manager
        self.db_manager = MagicMock()
        self.db_manager.dataChanged = MockSignal()
        
        # Create mock folder manager
        self.folder_manager = MagicMock()
        
        # Mock methods to return test data
        self.folder_manager.get_all_root_folders.return_value = self._generate_mock_folders()
        self.folder_manager.get_recordings_in_folder = self._mock_get_recordings
        self.folder_manager.get_recordings_not_in_folders = self._mock_get_unassigned_recordings
        
        # Create instance with mocks
        with patch('app.RecentRecordingsWidget.FolderManager') as mock_folder_manager, \
             patch('app.RecentRecordingsWidget.DatabaseManager') as mock_db_manager, \
             patch('app.RecentRecordingsWidget.QTreeWidget'), \
             patch('app.RecentRecordingsWidget.QTreeWidgetItem', MockQTreeWidgetItem), \
             patch('app.RecentRecordingsWidget.RecordingListItem', MockRecordingListItem):
            
            mock_folder_manager.instance.return_value = self.folder_manager
            mock_db_manager.instance.return_value = self.db_manager
            
            self.widget = UnifiedFolderListWidget(self.db_manager)
            
            # Initialize test data - recordings are mocked with overlap between folders
            self.recordings = self._generate_mock_recordings()
            self.folder_recording_map = self._distribute_recordings_to_folders()
    
    def _generate_mock_folders(self):
        """Generate mock folder data with 3 folders + subfolders."""
        folders = []
        for i in range(1, 4):
            folder = {
                'id': i,
                'name': f"Test Folder {i}",
                'children': []
            }
            
            # Add 2 children to folder 1
            if i == 1:
                for j in range(1, 3):
                    child_id = 10 + j
                    child = {
                        'id': child_id,
                        'name': f"Subfolder {j} of Folder {i}",
                        'children': []
                    }
                    folder['children'].append(child)
            
            folders.append(folder)
        
        return folders
    
    def _generate_mock_recordings(self):
        """Generate 20 mock recordings."""
        recordings = []
        for i in range(1, 21):
            rec_id = i
            rec = [
                rec_id,
                f"Recording_{rec_id}.mp3",
                f"/recordings/Recording_{rec_id}.mp3",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                f"00:{i:02d}",  # Duration
                f"Transcript for recording {rec_id}" if i % 2 == 0 else "",
                f"Processed text for recording {rec_id}" if i % 3 == 0 else ""
            ]
            recordings.append(rec)
        
        return recordings
    
    def _distribute_recordings_to_folders(self):
        """Distribute recordings across folders with deliberate overlap."""
        folder_map = {
            -1: [1, 2, 3],          # Unassigned
            1: [4, 5, 6, 7, 8],     # Folder 1
            2: [7, 8, 9, 10, 11],   # Folder 2 (overlap with 1: 7, 8)
            3: [11, 12, 13, 14],    # Folder 3 (overlap with 2: 11)
            11: [15, 16, 17],       # Subfolder 1 of Folder 1
            12: [17, 18, 19, 20]    # Subfolder 2 of Folder 1 (overlap with subfolder 1: 17)
        }
        return folder_map
    
    def _mock_get_recordings(self, folder_id, callback=None):
        """Mock implementation of get_recordings_in_folder."""
        rec_ids = self.folder_recording_map.get(folder_id, [])
        result = [rec for rec in self.recordings if rec[0] in rec_ids]
        
        if callback:
            callback(True, result)
        return result
    
    def _mock_get_unassigned_recordings(self, callback=None):
        """Mock implementation of get_recordings_not_in_folders."""
        return self._mock_get_recordings(-1, callback)
    
    def test_no_duplicates_after_refresh(self):
        """Test that refresh_all_folders() doesn't create duplicate recordings."""
        # Setup the widget with direct access to mock database
        with patch('app.RecentRecordingsWidget.FolderManager') as mock_folder_manager, \
             patch('app.RecentRecordingsWidget.DatabaseManager') as mock_db_manager, \
             patch('app.RecentRecordingsWidget.QTreeWidget'), \
             patch('app.RecentRecordingsWidget.QTreeWidgetItem', MockQTreeWidgetItem), \
             patch('app.RecentRecordingsWidget.RecordingListItem', MockRecordingListItem), \
             patch.object(UnifiedFolderListWidget, 'clear'), \
             patch.object(UnifiedFolderListWidget, 'itemAt'), \
             patch.object(UnifiedFolderListWidget, 'setCurrentItem'), \
             patch.object(UnifiedFolderListWidget, 'itemWidget', return_value=None), \
             patch.object(UnifiedFolderListWidget, 'removeItemWidget'), \
             patch.object(UnifiedFolderListWidget, 'setItemWidget'), \
             patch.object(UnifiedFolderListWidget, 'add_folder_to_tree',
                         return_value=MockQTreeWidgetItem()):
            
            mock_folder_manager.instance.return_value = self.folder_manager
            mock_db_manager.instance.return_value = self.db_manager
            
            # First load
            self.widget.load_structure()
            
            # Count total recordings across all folders
            total_recordings = len(set([rec[0] for rec in self.recordings]))
            
            # First verify: recordings_map should match number of unique recordings
            self.assertEqual(len(self.widget.recordings_map), total_recordings,
                            "recordings_map count should match unique recordings")
            
            # Second verify: Check seen_recording_ids
            self.assertEqual(len(self.widget.seen_recording_ids), total_recordings,
                           "seen_recording_ids count should match unique recordings")
            
            # First refresh
            self.widget.handle_data_changed()
            
            # Verify after refresh
            self.assertEqual(len(self.widget.recordings_map), total_recordings,
                            "recordings_map count should match unique recordings after refresh")
            self.assertEqual(len(self.widget.seen_recording_ids), total_recordings,
                           "seen_recording_ids count should match unique recordings after refresh")
            
            # Multiple refreshes - testing 5 consecutive refreshes
            for i in range(5):
                self.widget.handle_data_changed()
                # Verify after each refresh
                self.assertEqual(len(self.widget.recordings_map), total_recordings,
                               f"recordings_map count should remain consistent after refresh {i+1}")
                self.assertEqual(len(self.widget.seen_recording_ids), total_recordings,
                               f"seen_recording_ids count should remain consistent after refresh {i+1}")
    
    def test_clear_folder_recordings(self):
        """Test that _clear_folder_recordings properly cleans up widgets and tracking maps."""
        # Setup the widget with direct access to mock database
        with patch('app.RecentRecordingsWidget.FolderManager') as mock_folder_manager, \
             patch('app.RecentRecordingsWidget.DatabaseManager') as mock_db_manager, \
             patch('app.RecentRecordingsWidget.QTreeWidget'), \
             patch('app.RecentRecordingsWidget.QTreeWidgetItem', MockQTreeWidgetItem), \
             patch('app.RecentRecordingsWidget.RecordingListItem', MockRecordingListItem), \
             patch.object(UnifiedFolderListWidget, 'clear'), \
             patch.object(UnifiedFolderListWidget, 'itemAt'), \
             patch.object(UnifiedFolderListWidget, 'setCurrentItem'), \
             patch.object(UnifiedFolderListWidget, 'itemWidget', return_value=MockRecordingListItem(1, "", "", "")), \
             patch.object(UnifiedFolderListWidget, 'removeItemWidget'), \
             patch.object(UnifiedFolderListWidget, 'setItemWidget'), \
             patch.object(UnifiedFolderListWidget, 'add_folder_to_tree',
                         return_value=MockQTreeWidgetItem()):
            
            mock_folder_manager.instance.return_value = self.folder_manager
            mock_db_manager.instance.return_value = self.db_manager
            
            # First load to populate data
            self.widget.load_structure()
            
            # Get a folder item
            folder_item = MockQTreeWidgetItem()
            folder_item.tree_widget = self.widget
            folder_item.data_dict = {"type": "folder", "id": 1}
            
            # Create child recording items
            for i in range(1, 6):
                child = MockQTreeWidgetItem(folder_item)
                child.tree_widget = self.widget
                child.data_dict = {"type": "recording", "id": i}
                
                # Add to tracking maps
                self.widget.recordings_map[i] = MockRecordingListItem(i, f"rec_{i}.mp3", "", "")
                self.widget.item_map[("recording", i)] = child
                self.widget.seen_recording_ids.add(i)
            
            # Verify setup
            self.assertEqual(folder_item.childCount(), 5)
            self.assertEqual(len(self.widget.recordings_map), 20)  # All recordings
            
            # Call _clear_folder_recordings
            self.widget._clear_folder_recordings(folder_item)
            
            # Verify children were removed
            self.assertEqual(folder_item.childCount(), 0)
            
            # Verify tracking maps were updated
            for i in range(1, 6):
                self.assertNotIn(i, self.widget.recordings_map)
                self.assertNotIn(("recording", i), self.widget.item_map)
                self.assertNotIn(i, self.widget.seen_recording_ids)

if __name__ == '__main__':
    unittest.main()