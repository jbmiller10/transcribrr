#!/usr/bin/env python
"""Test script to validate uniqueness of recording items in UnifiedFolderTreeView."""

import os
import sys
import random
import time
import uuid
import unittest
from typing import List, Dict, Set, Any
from unittest.mock import patch, MagicMock, PropertyMock

# Add parent directory to path for relative imports 
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

# Create mocks for PyQt6 dependencies
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
        
    def setIcon(self, icon):
        pass
        
    def setFlags(self, flags):
        pass
        
    def flags(self):
        return 0
        
    def setForeground(self, column, color):
        pass

class MockRecordingListItem:
    def __init__(self, rec_id, filename, file_path, date_created, raw_transcript="", processed_text="", duration="00:00"):
        self.rec_id = rec_id
        self.filename = filename
        self.filename_no_ext = os.path.splitext(filename)[0]
        self.file_path = file_path
        self.date_created = date_created
        self.raw_transcript = raw_transcript
        self.processed_text = processed_text
        self.duration = duration
    
    def get_id(self):
        return self.rec_id
    
    def refresh_folders(self):
        pass
    
    def sizeHint(self):
        return (200, 50)

# Set up mocks before importing
import unittest.mock
sys.modules['PyQt6'] = unittest.mock.MagicMock()
sys.modules['PyQt6.QtWidgets'] = unittest.mock.MagicMock()
sys.modules['PyQt6.QtCore'] = unittest.mock.MagicMock() 
sys.modules['PyQt6.QtGui'] = unittest.mock.MagicMock()

# Create signal mock
class MockSignal:
    def __init__(self):
        self.connect = MagicMock()
        self.emit = MagicMock()

# Set up other mocks
from unittest.mock import patch, MagicMock

# Now import the module we want to test
with patch.dict('sys.modules', {
    'PyQt6': MagicMock(),
    'PyQt6.QtWidgets': MagicMock(),
    'PyQt6.QtCore': MagicMock(),
    'PyQt6.QtGui': MagicMock(),
}):
    # Add attributes to mocks
    sys.modules['PyQt6.QtCore'].pyqtSignal = lambda *args: MockSignal()
    sys.modules['PyQt6.QtWidgets'].QTreeView = MagicMock
    sys.modules['PyQt6.QtGui'].QStandardItem = MockQStandardItem
    
    # Import the module we want to test
    from app.UnifiedFolderTreeView import UnifiedFolderTreeView

class TestRecordingItemUniqueness(unittest.TestCase):
    """Test case for verifying uniqueness of recording items in UnifiedFolderTreeView."""
    
    def setUp(self):
        """Set up mock objects and UnifiedFolderTreeView instance."""
        # Mock FolderManager and DatabaseManager
        self.folder_manager = MagicMock()
        self.db_manager = MagicMock()
        
        # Mock methods for test data
        self.folder_manager.get_all_root_folders.return_value = self._generate_mock_folders(50)
        self.folder_manager.get_recordings_in_folder.side_effect = self._mock_recordings_in_folder
        self.folder_manager.get_recordings_not_in_folders.side_effect = self._mock_recordings_not_in_folders
        
        # Create instance with patches
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
            
            # Initialize test data
            self.generated_recordings = self._generate_mock_recordings(2000)
            self.folder_recording_map = self._distribute_recordings_to_folders(50)
    
    def _generate_mock_folders(self, count=10) -> List[Dict[str, Any]]:
        """Generate mock folder data."""
        folders = []
        for i in range(count):
            folder = {
                'id': i + 1,
                'name': f"Folder {i + 1}",
                'children': []
            }
            
            # Add some children to a few folders
            if i % 5 == 0:
                for j in range(3):
                    child_id = count + (i * 3) + j + 1
                    child = {
                        'id': child_id,
                        'name': f"Subfolder {j + 1} of Folder {i + 1}",
                        'children': []
                    }
                    folder['children'].append(child)
            
            folders.append(folder)
        
        return folders
    
    def _generate_mock_recordings(self, count=100) -> List[List[Any]]:
        """Generate mock recording data."""
        recordings = []
        for i in range(count):
            rec_id = i + 1
            filename = f"Recording_{rec_id}.mp3"
            file_path = f"/recordings/{filename}"
            date_created = "2023-01-01 12:00:00"
            raw_transcript = f"Transcript for recording {rec_id}" if i % 2 == 0 else ""
            processed_text = f"Processed text for recording {rec_id}" if i % 3 == 0 else ""
            
            recording = [rec_id, filename, file_path, date_created, raw_transcript, processed_text]
            recordings.append(recording)
        
        return recordings
    
    def _distribute_recordings_to_folders(self, folder_count=10) -> Dict[int, List[int]]:
        """Distribute recordings among folders with some overlap."""
        folder_recording_map = {-1: []}  # Start with root folder (-1)
        
        # Create the mapping
        for i in range(1, folder_count + 1):
            folder_recording_map[i] = []
        
        # Add some subfolder IDs
        for i in range(0, folder_count, 5):
            for j in range(3):
                subfolder_id = folder_count + (i * 3) + j + 1
                folder_recording_map[subfolder_id] = []
        
        # Distribute recordings
        for rec in self.generated_recordings:
            rec_id = rec[0]
            
            # 20% chance of being in root folder only
            if random.random() < 0.2:
                folder_recording_map[-1].append(rec_id)
                continue
                
            # Add to 1-3 folders with 10% chance of overlap
            assigned_folders = []
            for folder_id in folder_recording_map.keys():
                if folder_id == -1:
                    continue
                    
                if random.random() < 0.1 or not assigned_folders:
                    folder_recording_map[folder_id].append(rec_id)
                    assigned_folders.append(folder_id)
                    
                    # Limit to max 3 folders per recording
                    if len(assigned_folders) >= 3:
                        break
        
        return folder_recording_map
    
    def _mock_recordings_in_folder(self, folder_id, callback=None):
        """Mock implementation of get_recordings_in_folder."""
        result = []
        recording_ids = self.folder_recording_map.get(folder_id, [])
        
        for rec_id in recording_ids:
            # Find recording in generated list
            for rec in self.generated_recordings:
                if rec[0] == rec_id:
                    result.append(rec)
                    break
        
        if callback:
            callback(True, result)
        return result
    
    def _mock_recordings_not_in_folders(self, callback=None):
        """Mock implementation of get_recordings_not_in_folders."""
        result = self._mock_recordings_in_folder(-1, None)
        
        if callback:
            callback(True, result)
        return result
    
    def test_no_duplicate_recordings(self):
        """Test that loading structure doesn't create duplicate recordings."""
        # Override methods with test versions
        with patch.object(UnifiedFolderTreeView, 'setIndexWidget'), \
             patch.object(UnifiedFolderTreeView, 'setExpanded'):
            
            # Force synchronous execution of callbacks
            def execute_callback_immediately(folder_id, callback):
                result = self._mock_recordings_in_folder(folder_id)
                callback(True, result)
            
            def execute_root_callback_immediately(callback):
                result = self._mock_recordings_not_in_folders()
                callback(True, result)
            
            self.folder_manager.get_recordings_in_folder.side_effect = execute_callback_immediately
            self.folder_manager.get_recordings_not_in_folders.side_effect = execute_root_callback_immediately
            
            # Load structure
            self.widget.load_structure()
            
            # Check that all recordings were processed
            total_recordings = len(set([rec[0] for rec in self.generated_recordings]))
            print(f"Total unique recordings to load: {total_recordings}")
            print(f"Recordings in map: {len(self.widget.recordings_map)}")
            print(f"Seen recording IDs: {len(self.widget.seen_recording_ids)}")
            
            # Verify no duplicates by ensuring seen_recording_ids and recordings_map have the same length
            self.assertEqual(len(self.widget.seen_recording_ids), len(self.widget.recordings_map), 
                            "Mismatch between seen_recording_ids and recordings_map sizes indicates potential duplicates")
            
            # Now test successive refreshes
            print("\nTesting multiple refreshes...\n")
            for i in range(10):
                prev_map_size = len(self.widget.recordings_map)
                prev_seen_size = len(self.widget.seen_recording_ids)
                
                self.widget.load_structure()
                
                print(f"Refresh {i+1}:")
                print(f"  Previous recordings_map size: {prev_map_size}")
                print(f"  Previous seen_recording_ids size: {prev_seen_size}")
                print(f"  New recordings_map size: {len(self.widget.recordings_map)}")
                print(f"  New seen_recording_ids size: {len(self.widget.seen_recording_ids)}")
                
                # Verify map sizes are still equal after refresh
                self.assertEqual(len(self.widget.seen_recording_ids), len(self.widget.recordings_map),
                                f"After refresh {i+1}, mismatch between seen IDs and map size indicates problem")

if __name__ == '__main__':
    unittest.main()