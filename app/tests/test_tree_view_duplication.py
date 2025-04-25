import sys
import unittest
from unittest.mock import MagicMock, patch
import os
import time
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, Qt
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.UnifiedFolderTreeView import UnifiedFolderTreeView
from app.DatabaseManager import DatabaseManager
from app.FolderManager import FolderManager

# Mock class for generating delayed callbacks
class DelayedCallbackGenerator(QObject):
    callback_triggered = pyqtSignal(bool, list)
    
    def __init__(self):
        super().__init__()
        self.callbacks_pending = 0
        
    def generate_delayed_callback(self, data, delay_ms):
        """Generate a callback that will fire after delay_ms milliseconds"""
        self.callbacks_pending += 1
        
        def execute_callback():
            self.callback_triggered.emit(True, data)
            self.callbacks_pending -= 1
            
        QTimer.singleShot(delay_ms, execute_callback)
        
    def is_finished(self):
        """Check if all callbacks have been executed"""
        return self.callbacks_pending == 0


class TestTreeViewDuplication(unittest.TestCase):
    """Test cases for tree view duplication prevention."""
    
    @classmethod
    def setUpClass(cls):
        # Create QApplication instance if it doesn't exist
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()
            
    def setUp(self):
        # Create mock database manager with real signal
        class MockDBManager(QObject):
            dataChanged = pyqtSignal(str, int)
            
            def __init__(self):
                super().__init__()
                
        self.db_manager = MockDBManager()
        
        # Create mock folder manager with real signals
        class MockFolderManager(QObject):
            operation_complete = pyqtSignal(bool, list)
            error_occurred = pyqtSignal(str, str)
            
            def __init__(self):
                super().__init__()
                
            def get_all_root_folders(self):
                return [
                    {"id": 1, "name": "Folder 1", "parent_id": None, "children": []},
                    {"id": 2, "name": "Folder 2", "parent_id": None, "children": []}
                ]
                
            def get_recordings_not_in_folders(self, callback):
                # Will be mocked later
                pass
                
            def get_recordings_in_folder(self, folder_id, callback):
                # Will be mocked later
                pass
                
        self.folder_manager = MockFolderManager()
        FolderManager._instance = self.folder_manager
        
        # Track the last callback set for each function
        self.callbacks = {
            "unassigned": None,
            "folder1": None,
            "folder2": None
        }
        
    def _dispatch_callback(self, success, data):
        """Dispatch callback data to the appropriate function based on the data content"""
        if not data:
            return
            
        # Use the first recording ID to determine which callback to call
        first_rec_id = data[0][0]
        
        if first_rec_id < 4:  # Unassigned recordings
            self.callbacks["unassigned"](success, data)
        elif first_rec_id < 7:  # Folder 1 recordings
            self.callbacks["folder1"](success, data)
        else:  # Folder 2 recordings
            self.callbacks["folder2"](success, data)
        
        # Setup mock folder data
        root_folders = [
            {"id": 1, "name": "Folder 1", "parent_id": None, "children": []},
            {"id": 2, "name": "Folder 2", "parent_id": None, "children": []}
        ]
        self.folder_manager.get_all_root_folders.return_value = root_folders
        
        # Create test recordings for unassigned and folders
        self.unassigned_recordings = []
        self.folder1_recordings = []
        self.folder2_recordings = []
        
        # Generate sample recordings for testing
        for i in range(10):
            rec = [
                i,  # id
                f"Recording {i}",  # filename
                f"/path/to/recording_{i}.mp3",  # file_path
                "2023-10-01 10:00:00",  # date_created
                "02:30",  # duration
                "Sample transcript",  # raw_transcript
                "Processed text",  # processed_text
                None,  # raw_transcript_formatted
                None   # processed_text_formatted
            ]
            
            if i < 4:
                self.unassigned_recordings.append(rec)
            elif i < 7:
                self.folder1_recordings.append(rec)
            else:
                self.folder2_recordings.append(rec)
        
        # Create callback generator for delayed responses
        self.callback_generator = DelayedCallbackGenerator()
        
        # Move any children that were copied when the EditTool replaced text above
        if hasattr(self, 'folders') and not isinstance(self.folders, list):
            del self.folders
        
        # Create tree view with mocked dependencies
        self.tree_view = UnifiedFolderTreeView(self.db_manager)
        
    def tearDown(self):
        # Clean up resources
        if hasattr(self, 'tree_view'):
            self.tree_view.deleteLater()
        
    def test_overlapping_callbacks(self):
        """Test that overlapping callbacks don't create duplicate items."""
        # Setup mock responses
        
        # Mock unassigned recordings function
        def mock_get_recordings_not_in_folders(callback):
            # Store the callback
            self.callbacks["unassigned"] = callback
            # Generate a delayed callback
            self.callback_generator.generate_delayed_callback(self.unassigned_recordings, 100)
            
        # Mock folder recordings function
        def mock_get_recordings_in_folder(folder_id, callback):
            # Store the callback based on folder ID
            if folder_id == 1:
                self.callbacks["folder1"] = callback
                # Generate a delayed callback
                self.callback_generator.generate_delayed_callback(
                    self.folder1_recordings, 200  # Slower response
                )
            else:
                self.callbacks["folder2"] = callback
                # Generate a delayed callback
                self.callback_generator.generate_delayed_callback(
                    self.folder2_recordings, 50  # Faster response
                )
            
        # Set up the mocks
        self.folder_manager.get_recordings_not_in_folders = mock_get_recordings_not_in_folders
        self.folder_manager.get_recordings_in_folder = mock_get_recordings_in_folder
            
        # Connect delayed callback generator to appropriate callbacks based on type
        self.callback_generator.callback_triggered.connect(
            lambda success, data: self._dispatch_callback(success, data),
            Qt.ConnectionType.QueuedConnection
        )
        
        # Trigger a load operation
        self.tree_view.load_structure()
        
        # Before callbacks finish, trigger another load operation
        QTimer.singleShot(20, self.tree_view.load_structure)
        
        # Process events until all callbacks are finished
        while not self.callback_generator.is_finished():
            QTest.qWait(50)  # Wait a bit for callbacks to complete
            QApplication.processEvents()
            
        # Process final events
        QTest.qWait(300)
        QApplication.processEvents()
        
        # Verify no duplicate items in the model
        # Get all recording IDs from the model
        recording_ids = set()
        for item_key in self.tree_view.source_model.item_map.keys():
            if item_key[0] == "recording":
                recording_ids.add(item_key[1])
                
        # Check that we have exactly the number of unique recordings
        all_recs = self.unassigned_recordings + self.folder1_recordings + self.folder2_recordings
        expected_ids = {rec[0] for rec in all_recs}
        
        self.assertEqual(len(recording_ids), len(expected_ids),
                         f"Found {len(recording_ids)} recordings in model, expected {len(expected_ids)}")
        
        # Also check that id_to_widget map matches exactly
        self.assertEqual(len(self.tree_view.id_to_widget), len(expected_ids),
                        "Widget map count doesn't match expected recording count")
                        
        # Check that each ID appears exactly once                
        for rec_id in expected_ids:
            self.assertIn(("recording", rec_id), self.tree_view.source_model.item_map,
                         f"Recording {rec_id} missing from model")
            self.assertIn(rec_id, self.tree_view.id_to_widget,
                         f"Recording {rec_id} missing from widget map")
                         
    def test_token_invalidation(self):
        """Test that load tokens properly invalidate stale callbacks."""
        # Get initial token
        initial_token = self.tree_view._load_token
        
        # Setup empty response mocks
        def empty_callback(callback):
            self.callbacks["unassigned"] = callback
            
        def empty_folder_callback(folder_id, callback):
            if folder_id == 1:
                self.callbacks["folder1"] = callback
            else:
                self.callbacks["folder2"] = callback
                
        self.folder_manager.get_recordings_not_in_folders = empty_callback
        self.folder_manager.get_recordings_in_folder = empty_folder_callback
        
        # Trigger load to increment token
        self.tree_view.load_structure()
        
        # Save the callbacks from the first load
        first_unassigned_callback = self.callbacks["unassigned"]
        
        # Verify token was incremented
        self.assertEqual(self.tree_view._load_token, initial_token + 1,
                        "Load token should be incremented during load_structure")
        
        # Trigger load again to increment token again
        self.tree_view.load_structure()
        
        # Verify token was incremented
        self.assertEqual(self.tree_view._load_token, initial_token + 2,
                        "Load token should be incremented again")
        
        # Now execute the callback from the first load with the now-stale token
        if first_unassigned_callback:
            first_unassigned_callback(True, self.unassigned_recordings)
        
        # Process events
        QTest.qWait(50)
        QApplication.processEvents()
        
        # Verify no recordings were added from stale callback
        recording_ids = set()
        for item_key in self.tree_view.source_model.item_map.keys():
            if item_key[0] == "recording":
                recording_ids.add(item_key[1])
                
        self.assertEqual(len(recording_ids), 0,
                         "Stale callback should not add any recordings to model")
                         
        self.assertEqual(len(self.tree_view.id_to_widget), 0,
                        "Stale callback should not add any widgets to map")

if __name__ == '__main__':
    unittest.main()