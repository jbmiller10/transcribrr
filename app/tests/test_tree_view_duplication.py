# app/tests/test_tree_view_duplication.py
import sys
import unittest
from unittest.mock import MagicMock, patch
import os
import time # Import time module
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, Qt
from PyQt6.QtWidgets import QApplication
# REMOVE the QTest import
# from PyQt6.QtTest import QTest

# Add parent directory to path to import app modules
# Ensure this path adjustment is correct for your structure
if os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")) not in sys.path:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

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
            # Check if the instance still exists before emitting
            if self:
                self.callback_triggered.emit(True, data)
                self.callbacks_pending -= 1

        QTimer.singleShot(delay_ms, execute_callback)

    def is_finished(self):
        """Check if all callbacks have been executed"""
        return self.callbacks_pending <= 0


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
            operation_complete = pyqtSignal(bool, list) # Simulate FolderManager signal if needed
            error_occurred = pyqtSignal(str, str)     # Simulate FolderManager signal if needed

            def __init__(self):
                super().__init__()

            def get_all_root_folders(self):
                # Provide some default folders for structure loading
                return [
                    {"id": 1, "name": "Folder 1", "parent_id": None, "children": []},
                    {"id": 2, "name": "Folder 2", "parent_id": None, "children": []}
                ]

            def get_recordings_not_in_folders(self, callback):
                # Will be mocked in the test method
                pass

            def get_recordings_in_folder(self, folder_id, callback):
                # Will be mocked in the test method
                pass

        self.folder_manager = MockFolderManager()
        # Patch the singleton instance directly for the test duration if necessary
        # This avoids issues if FolderManager.instance() was called elsewhere before patch
        self._original_folder_manager_instance = FolderManager._instance
        FolderManager._instance = self.folder_manager


        # Track the last callback set for each function
        self.callbacks = {
            "unassigned": None,
            "folder1": None,
            "folder2": None
        }

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

        # Create tree view with mocked dependencies
        self.tree_view = UnifiedFolderTreeView(self.db_manager)

    def tearDown(self):
        # Restore original singleton instance if patched
        if hasattr(self, '_original_folder_manager_instance'):
             FolderManager._instance = self._original_folder_manager_instance

        # Clean up resources
        if hasattr(self, 'tree_view'):
            self.tree_view.deleteLater()
        # Process events to ensure cleanup happens
        QApplication.processEvents()


    def _dispatch_callback(self, success, data):
        """Dispatch callback data to the appropriate function based on the data content"""
        if not data:
            print("DEBUG: Dispatch received empty data")
            return

        # Use the first recording ID to determine which callback to call
        try:
            first_rec_id = data[0][0]
            print(f"DEBUG: Dispatching callback for data starting with ID {first_rec_id}")

            if first_rec_id < 4:  # Unassigned recordings
                if self.callbacks["unassigned"]:
                    print("DEBUG: Calling unassigned callback")
                    self.callbacks["unassigned"](success, data)
                else: print("DEBUG: No unassigned callback registered")
            elif first_rec_id < 7:  # Folder 1 recordings
                if self.callbacks["folder1"]:
                    print("DEBUG: Calling folder1 callback")
                    self.callbacks["folder1"](success, data)
                else: print("DEBUG: No folder1 callback registered")
            else:  # Folder 2 recordings
                if self.callbacks["folder2"]:
                    print("DEBUG: Calling folder2 callback")
                    self.callbacks["folder2"](success, data)
                else: print("DEBUG: No folder2 callback registered")
        except IndexError:
             print("DEBUG: Dispatch received data with unexpected format (IndexError)")
        except Exception as e:
             print(f"DEBUG: Error during callback dispatch: {e}")


    def test_overlapping_callbacks(self):
        """Test that overlapping callbacks don't create duplicate items."""
        print("\n--- Starting test_overlapping_callbacks ---")
        # Setup mock responses

        # Mock unassigned recordings function
        def mock_get_recordings_not_in_folders(callback):
            print("DEBUG: mock_get_recordings_not_in_folders called, scheduling callback")
            self.callbacks["unassigned"] = callback
            self.callback_generator.generate_delayed_callback(self.unassigned_recordings, 150) # Increased delay

        # Mock folder recordings function
        def mock_get_recordings_in_folder(folder_id, callback):
            print(f"DEBUG: mock_get_recordings_in_folder called for ID {folder_id}, scheduling callback")
            if folder_id == 1:
                self.callbacks["folder1"] = callback
                self.callback_generator.generate_delayed_callback(self.folder1_recordings, 250) # Slower
            elif folder_id == 2:
                self.callbacks["folder2"] = callback
                self.callback_generator.generate_delayed_callback(self.folder2_recordings, 100) # Faster
            else:
                 print(f"Warning: mock_get_recordings_in_folder called with unexpected folder_id: {folder_id}")


        # Set up the mocks
        self.folder_manager.get_recordings_not_in_folders = mock_get_recordings_not_in_folders
        self.folder_manager.get_recordings_in_folder = mock_get_recordings_in_folder

        # Connect delayed callback generator to the dispatcher
        self.callback_generator.callback_triggered.connect(
            lambda success, data: self._dispatch_callback(success, data),
            Qt.ConnectionType.QueuedConnection # Ensure it runs in the event loop
        )

        # Trigger a load operation
        print("DEBUG: Triggering first load_structure")
        self.tree_view.load_structure()
        QApplication.processEvents() # Let the initial structure build start

        # Before callbacks finish, trigger another load operation quickly
        print("DEBUG: Scheduling second load_structure")
        QTimer.singleShot(50, lambda: (print("DEBUG: Triggering second load_structure"), self.tree_view.load_structure()))

        # Process events until all callbacks are finished
        start_time = time.time()
        print("DEBUG: Entering wait loop for callbacks")
        processed_events_count = 0
        while not self.callback_generator.is_finished():
            # --- FIX: Replace QTest.qWait ---
            time.sleep(0.05) # Sleep for 50 milliseconds
            QApplication.processEvents() # Still process Qt events
            processed_events_count += 1
            # --- End FIX ---
            if time.time() - start_time > 10: # Increased Timeout
                self.fail(f"Timeout waiting for callbacks to finish. {self.callback_generator.callbacks_pending} callbacks pending.")
        print(f"DEBUG: Callback wait loop finished after {time.time() - start_time:.2f}s and {processed_events_count} processEvents calls.")


        # Process final events generously
        print("DEBUG: Processing final events...")
        for _ in range(10): # Process multiple times
            time.sleep(0.1)
            QApplication.processEvents()
        print("DEBUG: Final event processing done.")


        # --- Verification ---
        print("DEBUG: Starting verification...")
        # Get all recording IDs from the model
        recording_ids_in_model = set()
        items_in_map = self.tree_view.source_model.item_map # Get the map
        for item_key in items_in_map.keys():
            if item_key[0] == "recording":
                recording_ids_in_model.add(item_key[1])
        print(f"DEBUG: Recording IDs found in source_model.item_map: {recording_ids_in_model}")

        # Get all recording IDs from the widget map
        recording_ids_in_widget_map = set(self.tree_view.id_to_widget.keys())
        print(f"DEBUG: Recording IDs found in id_to_widget map: {recording_ids_in_widget_map}")


        # Check that we have exactly the number of unique recordings
        all_recs = self.unassigned_recordings + self.folder1_recordings + self.folder2_recordings
        expected_ids = {rec[0] for rec in all_recs}
        print(f"DEBUG: Expected Recording IDs: {expected_ids}")

        self.assertEqual(len(recording_ids_in_model), len(expected_ids),
                         f"Found {len(recording_ids_in_model)} unique recordings in model map, expected {len(expected_ids)}")

        self.assertEqual(len(recording_ids_in_widget_map), len(expected_ids),
                        f"Widget map count ({len(recording_ids_in_widget_map)}) doesn't match expected recording count ({len(expected_ids)})")

        # Check that each ID appears exactly once
        for rec_id in expected_ids:
            self.assertIn(("recording", rec_id), items_in_map,
                         f"Recording {rec_id} missing from model map")
            self.assertIn(rec_id, recording_ids_in_widget_map,
                         f"Recording {rec_id} missing from widget map")
        print("--- Finished test_overlapping_callbacks ---")


    def test_token_invalidation(self):
        """Test that load tokens properly invalidate stale callbacks."""
        print("\n--- Starting test_token_invalidation ---")
        # Get initial token
        initial_token = self.tree_view._load_token
        print(f"DEBUG: Initial load token: {initial_token}")

        # Setup empty response mocks that just store the callback
        def empty_callback_unassigned(callback):
            print("DEBUG: empty_callback_unassigned called")
            self.callbacks["unassigned"] = callback

        def empty_folder_callback(folder_id, callback):
             print(f"DEBUG: empty_folder_callback called for ID {folder_id}")
             if folder_id == 1: self.callbacks["folder1"] = callback
             elif folder_id == 2: self.callbacks["folder2"] = callback

        self.folder_manager.get_recordings_not_in_folders = empty_callback_unassigned
        self.folder_manager.get_recordings_in_folder = empty_folder_callback

        # Trigger load to increment token
        print("DEBUG: Triggering first load_structure")
        self.tree_view.load_structure()
        QApplication.processEvents() # Process events to ensure load starts

        # Save the callback from the first load
        first_unassigned_callback = self.callbacks["unassigned"]
        self.assertIsNotNone(first_unassigned_callback, "Callback for first load was not captured")

        # Verify token was incremented
        self.assertEqual(self.tree_view._load_token, initial_token + 1,
                        "Load token should be incremented after first load")
        print(f"DEBUG: Token after first load: {self.tree_view._load_token}")

        # Trigger load again to increment token again
        print("DEBUG: Triggering second load_structure")
        self.tree_view.load_structure()
        QApplication.processEvents() # Process events

        # Verify token was incremented
        self.assertEqual(self.tree_view._load_token, initial_token + 2,
                        "Load token should be incremented again after second load")
        print(f"DEBUG: Token after second load: {self.tree_view._load_token}")

        # Now execute the callback from the first load with the now-stale token
        print("DEBUG: Executing stale callback from first load")
        first_unassigned_callback(True, self.unassigned_recordings)

        # Process events to allow the (stale) callback signal to be handled
        print("DEBUG: Processing events after stale callback execution")
        # --- FIX: Replace QTest.qWait ---
        time.sleep(0.1) # Sleep for 100 milliseconds
        QApplication.processEvents()
        # --- End FIX ---
        print("DEBUG: Event processing done.")

        # Verify no recordings were added from stale callback
        recording_ids_in_model = set()
        for item_key in self.tree_view.source_model.item_map.keys():
            if item_key[0] == "recording":
                recording_ids_in_model.add(item_key[1])

        self.assertEqual(len(recording_ids_in_model), 0,
                         f"Stale callback should not add any recordings to model, found: {recording_ids_in_model}")

        self.assertEqual(len(self.tree_view.id_to_widget), 0,
                        "Stale callback should not add any widgets to map")
        print("--- Finished test_token_invalidation ---")


if __name__ == '__main__':
    unittest.main()
