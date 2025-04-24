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
class MockQModelIndex:
    def __init__(self, valid=True, row=0, column=0, parent=None):
        self.valid = valid
        self.row_value = row
        self.column_value = column
        self.parent_index = parent
        
    def isValid(self):
        return self.valid
        
    def row(self):
        return self.row_value
        
    def column(self):
        return self.column_value
        
    def parent(self):
        return self.parent_index or MockQModelIndex(valid=False)
        
class MockQStandardItem:
    def __init__(self):
        self.children = []
        self.data_dict = {}
        self.text_value = ""
        self.row_count = 0
        
    def index(self):
        return MockQModelIndex()
        
    def child(self, row, column=0):
        if 0 <= row < len(self.children):
            return self.children[row]
        return None
        
    def data(self, role):
        return self.data_dict.get(role, None)
        
    def setData(self, role, value):
        self.data_dict[role] = value
        
    def setText(self, text):
        self.text_value = text
        
    def text(self):
        return self.text_value
        
    def rowCount(self):
        return self.row_count
        
    def appendRow(self, items):
        if not isinstance(items, list):
            items = [items]
        self.children.extend(items)
        self.row_count += 1

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
    sys.modules['PyQt6.QtWidgets'].QTreeView = MagicMock
    sys.modules['PyQt6.QtGui'].QStandardItem = MockQStandardItem
    
    # Import the module to test
    from app.UnifiedFolderTreeView import UnifiedFolderTreeView

class TestRecordingDuplicates(unittest.TestCase):
    """Test case for verifying no duplicate recordings in UnifiedFolderTreeView."""
    
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
        with patch('app.UnifiedFolderTreeView.FolderManager') as mock_folder_manager, \
             patch('app.UnifiedFolderTreeView.DatabaseManager') as mock_db_manager, \
             patch('app.UnifiedFolderTreeView.QTreeView'), \
             patch('app.RecordingFolderModel.RecordingFolderModel') as mock_model, \
             patch('app.RecordingFolderModel.RecordingFilterProxyModel') as mock_proxy, \
             patch('app.UnifiedFolderTreeView.RecordingListItem', MockRecordingListItem):
            
            mock_folder_manager.instance.return_value = self.folder_manager
            mock_db_manager.instance.return_value = self.db_manager
            
            # Create mock model and proxy model
            self.mock_model = MagicMock()
            self.mock_proxy = MagicMock()
            mock_model.return_value = self.mock_model
            mock_proxy.return_value = self.mock_proxy
            
            # Setup model methods
            self.mock_model.item_map = {}
            self.mock_model.clear_model = MagicMock()
            self.mock_model.add_folder_item = MagicMock(return_value=MockQStandardItem())
            self.mock_model.add_recording_item = MagicMock(return_value=MockQStandardItem())
            
            # Setup proxy methods
            self.mock_proxy.mapFromSource = MagicMock(return_value=MockQModelIndex())
            self.mock_proxy.mapToSource = MagicMock(return_value=MockQModelIndex())
            
            self.widget = UnifiedFolderTreeView(self.db_manager)
            
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
        with patch('app.UnifiedFolderTreeView.FolderManager') as mock_folder_manager, \
             patch('app.UnifiedFolderTreeView.DatabaseManager') as mock_db_manager, \
             patch('app.UnifiedFolderTreeView.QTreeView'), \
             patch('app.RecordingFolderModel.RecordingFolderModel') as mock_model, \
             patch('app.RecordingFolderModel.RecordingFilterProxyModel') as mock_proxy, \
             patch('app.UnifiedFolderTreeView.RecordingListItem', MockRecordingListItem), \
             patch.object(UnifiedFolderTreeView, 'setIndexWidget'), \
             patch.object(UnifiedFolderTreeView, 'setExpanded'):
            
            mock_folder_manager.instance.return_value = self.folder_manager
            mock_db_manager.instance.return_value = self.db_manager
            
            # Create mock model and proxy model
            self.mock_model = MagicMock()
            self.mock_proxy = MagicMock()
            mock_model.return_value = self.mock_model
            mock_proxy.return_value = self.mock_proxy
            
            # Setup model methods
            self.mock_model.item_map = {}
            self.mock_model.clear_model = MagicMock()
            self.mock_model.add_folder_item = MagicMock(return_value=MockQStandardItem())
            self.mock_model.add_recording_item = MagicMock(return_value=MockQStandardItem())
            
            # Setup proxy methods
            self.mock_proxy.mapFromSource = MagicMock(return_value=MockQModelIndex())
            self.mock_proxy.mapToSource = MagicMock(return_value=MockQModelIndex())
            
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
    
    def test_maps_are_in_sync(self):
        """Test that the tracking maps (recordings_map and seen_recording_ids) stay in sync."""
        # Setup the widget with direct access to mock database
        with patch('app.UnifiedFolderTreeView.FolderManager') as mock_folder_manager, \
             patch('app.UnifiedFolderTreeView.DatabaseManager') as mock_db_manager, \
             patch('app.UnifiedFolderTreeView.QTreeView'), \
             patch('app.RecordingFolderModel.RecordingFolderModel') as mock_model, \
             patch('app.RecordingFolderModel.RecordingFilterProxyModel') as mock_proxy, \
             patch('app.UnifiedFolderTreeView.RecordingListItem', MockRecordingListItem), \
             patch.object(UnifiedFolderTreeView, 'setIndexWidget'), \
             patch.object(UnifiedFolderTreeView, 'setExpanded'):
            
            mock_folder_manager.instance.return_value = self.folder_manager
            mock_db_manager.instance.return_value = self.db_manager
            
            # Create mock model and proxy model
            self.mock_model = MagicMock()
            self.mock_proxy = MagicMock()
            mock_model.return_value = self.mock_model
            mock_proxy.return_value = self.mock_proxy
            
            # Setup model methods
            self.mock_model.item_map = {}
            self.mock_model.clear_model = MagicMock()
            self.mock_model.add_folder_item = MagicMock(return_value=MockQStandardItem())
            self.mock_model.add_recording_item = MagicMock(return_value=MockQStandardItem())
            
            # Setup proxy methods
            self.mock_proxy.mapFromSource = MagicMock(return_value=MockQModelIndex())
            self.mock_proxy.mapToSource = MagicMock(return_value=MockQModelIndex())
            
            # First load to populate data
            self.widget.load_structure()
            
            # Add recordings to the tracking maps for testing
            for i in range(1, 6):
                self.widget.recordings_map[i] = MockRecordingListItem(i, f"rec_{i}.mp3", "", "")
                self.widget.seen_recording_ids.add(i)
            
            # Verify setup
            self.assertEqual(len(self.widget.recordings_map), 20)  # All recordings
            self.assertEqual(len(self.widget.seen_recording_ids), 20)  # All recordings
            
            # Clear the recordings_map and verify seen_recording_ids is also cleared during load_structure
            self.widget.load_structure()
            
            # Verify tracking maps were cleared
            self.assertEqual(len(self.widget.recordings_map), 20)  # Refreshed to 20 recordings
            self.assertEqual(len(self.widget.seen_recording_ids), 20)  # Refreshed to 20 recordings
            self.assertEqual(set(self.widget.recordings_map.keys()), self.widget.seen_recording_ids, 
                           "recordings_map and seen_recording_ids should contain the same recording IDs")

if __name__ == '__main__':
    unittest.main()