# app/tests/test_tree_view_duplication.py
import sys
import unittest
from unittest.mock import MagicMock, patch, call # Import call if needed for assertions
import os
import time
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, Qt
from PyQt6.QtWidgets import QApplication

# Add parent directory to path if needed
if os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")) not in sys.path:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# --- FIX: Add the missing class definition back ---
# Mock class for generating delayed callbacks
class DelayedCallbackGenerator(QObject):
    callback_triggered = pyqtSignal(bool, list, int) # Add token to signal

    def __init__(self):
        super().__init__()
        self.pending_callbacks = 0 # Use a simple counter

    def generate_delayed_callback(self, data, delay_ms, token):
        self.pending_callbacks += 1
        # Use lambda to capture current values of data and token
        QTimer.singleShot(delay_ms, lambda d=data, t=token: self._emit_callback(d, t))

    def _emit_callback(self, data, token):
        if self: # Check if instance still exists
            self.callback_triggered.emit(True, data, token)
            if self.pending_callbacks > 0: # Prevent going negative if called after cleanup
                 self.pending_callbacks -= 1

    def is_finished(self):
        return self.pending_callbacks <= 0
# --- End FIX ---

from app.UnifiedFolderTreeView import UnifiedFolderTreeView
# Import FolderManager only needed if patching methods directly on it (not needed with instance patching)
# from app.FolderManager import FolderManager


class TestTreeViewDuplication(unittest.TestCase):
    """Test cases for tree view duplication prevention."""

    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        # No patchers started here anymore

        # Prepare test data (remains the same)
        self.unassigned_recordings = [[i, f"Rec U{i}", f"/path/u{i}.mp3", "2023-10-01 10:00:00", "01:00", f"T{i}", "", None, None] for i in range(3)]
        self.folder1_recordings = [[i+3, f"Rec F1_{i}", f"/path/f1_{i}.mp3", "2023-10-02 11:00:00", "01:30", f"T{i+3}", "", None, None] for i in range(2)]
        self.folder2_recordings = [[i+5, f"Rec F2_{i}", f"/path/f2_{i}.mp3", "2023-10-03 12:00:00", "02:00", f"T{i+5}", "", None, None] for i in range(3)]
        self.all_recording_data = self.unassigned_recordings + self.folder1_recordings + self.folder2_recordings
        self.expected_ids = {rec[0] for rec in self.all_recording_data}

        # Root folders data for the mock
        self.mock_root_folders = [
            {"id": 1, "name": "Folder 1", "parent_id": None, "children": []},
            {"id": 2, "name": "Folder 2", "parent_id": None, "children": []}
        ]

        # Callback generator
        self.callback_generator = DelayedCallbackGenerator()

        # TreeView instance will be created within each test method now

    def tearDown(self):
        # No patchers to stop here
        # Clean up tree_view if created by a test method
        if hasattr(self, 'tree_view') and self.tree_view:
             self.tree_view.deleteLater()
             self.tree_view = None # Help garbage collection
        QApplication.processEvents() # Ensure cleanup

    def wait_for_callbacks(self, timeout=10):
        """Helper to wait for delayed callbacks."""
        start_time = time.time()
        processed_count = 0
        while not self.callback_generator.is_finished():
            time.sleep(0.05)
            QApplication.processEvents()
            processed_count += 1
            if time.time() - start_time > timeout:
                self.fail(f"Timeout waiting for callbacks. Pending: {self.callback_generator.pending_callbacks}")
        # Process final events
        time.sleep(0.1)
        QApplication.processEvents()
        print(f"DEBUG: Callbacks finished after {time.time() - start_time:.2f}s, {processed_count} loops.")


    # --- Test Method for Refresh Logic ---
    # --- FIX: Use decorators for patching ---
    @patch('app.UnifiedFolderTreeView.FolderManager', autospec=True) # Patch where FolderManager is IMPORTED/USED
    @patch('app.UnifiedFolderTreeView.DatabaseManager', autospec=True) # Patch where DatabaseManager is IMPORTED/USED
    def test_model_refresh_without_duplicates(self, MockDatabaseManager, MockFolderManager):
        """Test that refreshing the model doesn't create duplicates."""
        print("\n--- Starting test_model_refresh_without_duplicates ---")

        # --- Get Mock Instances from decorators ---
        mock_db_instance = MockDatabaseManager.return_value
        mock_folder_instance = MockFolderManager.instance.return_value # Access the singleton instance

        # --- Ensure Mock Instances have necessary attributes (like signals) ---
        # It's crucial signals exist *before* the class under test tries to connect to them
        mock_db_instance.dataChanged = pyqtSignal(str, int)
        # Add signals for mock_folder_instance if UnifiedFolderTreeView connects to them

        # --- Configure Mocks on the INSTANCE ---
        mock_folder_instance.get_all_root_folders.return_value = self.mock_root_folders

        callback_map = {} # Store callbacks to be triggered

        def side_effect_unassigned(callback):
            print("DEBUG: side_effect_unassigned called")
            callback_map['unassigned'] = callback
            self.callback_generator.generate_delayed_callback(
                self.unassigned_recordings, 50, self.tree_view._load_token
            )
        mock_folder_instance.get_recordings_not_in_folders.side_effect = side_effect_unassigned

        def side_effect_folders(folder_id, callback):
            print(f"DEBUG: side_effect_folders called for ID {folder_id}")
            key = f'folder{folder_id}'
            callback_map[key] = callback
            data = self.folder1_recordings if folder_id == 1 else self.folder2_recordings
            delay = 100 if folder_id == 1 else 75
            self.callback_generator.generate_delayed_callback(
                data, delay, self.tree_view._load_token
            )
        mock_folder_instance.get_recordings_in_folder.side_effect = side_effect_folders

        # Connect generator signal to trigger stored callbacks IF token matches
        # (dispatch_if_valid remains the same as previous version)
        def dispatch_if_valid(success, data, trigger_token):
             if not self.tree_view: return # Prevent errors during teardown
             if not data: return
             current_token = self.tree_view._load_token
             if trigger_token == current_token: # Check token validity
                  first_rec_id = data[0][0]
                  key = None
                  if first_rec_id < 3: key = "unassigned"
                  elif 3 <= first_rec_id < 5: key = "folder1"
                  elif first_rec_id >= 5: key = "folder2"

                  if key and key in callback_map and callback_map[key]:
                       print(f"DEBUG: Dispatching valid callback (token {trigger_token}) for key '{key}'")
                       callback_map[key](success, data) # Call the stored callback
                  else:
                       print(f"DEBUG: No valid callback found for key '{key}' or data.")
             else:
                  print(f"DEBUG: Ignoring stale callback (trigger token {trigger_token}, current {current_token})")

        # Ensure connection is robust
        try:
            self.callback_generator.callback_triggered.disconnect()
        except TypeError: pass # Ignore if not connected
        self.callback_generator.callback_triggered.connect(dispatch_if_valid)

        # --- Initialize TreeView INSIDE the test method ---
        self.tree_view = UnifiedFolderTreeView(mock_db_instance)
        QApplication.processEvents()

        # --- First Load ---
        print("DEBUG: Triggering first load_structure")
        self.tree_view.load_structure()
        self.wait_for_callbacks() # Wait for first load to complete

        # --- Verification after first load ---
        print("DEBUG: Verifying after first load...")
        recording_ids_in_model1 = {k[1] for k in self.tree_view.source_model.item_map if k[0] == "recording"}
        recording_ids_in_widget_map1 = set(self.tree_view.id_to_widget.keys())
        self.assertEqual(len(recording_ids_in_model1), len(self.expected_ids), "Model count mismatch after first load")
        self.assertEqual(len(recording_ids_in_widget_map1), len(self.expected_ids), "Widget map count mismatch after first load")
        print("DEBUG: Verification after first load PASSED.")

        # --- Second Load (Refresh) ---
        print("DEBUG: Triggering second load_structure (refresh)")
        # Reset mock call counts before second load if needed for specific assertions
        mock_folder_instance.get_recordings_not_in_folders.reset_mock()
        mock_folder_instance.get_recordings_in_folder.reset_mock()
        callback_map.clear() # Clear old callbacks before triggering new ones

        self.tree_view.load_structure()
        self.wait_for_callbacks() # Wait for second load to complete

        # --- Verification after second load ---
        print("DEBUG: Verifying after second load...")
        recording_ids_in_model2 = {k[1] for k in self.tree_view.source_model.item_map if k[0] == "recording"}
        recording_ids_in_widget_map2 = set(self.tree_view.id_to_widget.keys())

        self.assertEqual(len(recording_ids_in_model2), len(self.expected_ids), "Model count mismatch after second load")
        self.assertEqual(len(recording_ids_in_widget_map2), len(self.expected_ids), "Widget map count mismatch after second load")
        self.assertSetEqual(recording_ids_in_model2, self.expected_ids, "Model IDs mismatch after second load")
        self.assertSetEqual(recording_ids_in_widget_map2, self.expected_ids, "Widget map IDs mismatch after second load")
        print("--- Finished test_model_refresh_without_duplicates ---")


    # --- Test Method for Token Invalidation ---
    # --- FIX: Use decorators for patching ---
    @patch('app.UnifiedFolderTreeView.FolderManager', autospec=True)
    @patch('app.UnifiedFolderTreeView.DatabaseManager', autospec=True)
    def test_token_invalidation(self, MockDatabaseManager, MockFolderManager):
        """Test that load tokens properly invalidate stale callbacks."""
        print("\n--- Starting test_token_invalidation ---")

        # --- Get Mock Instances ---
        mock_db_instance = MockDatabaseManager.return_value
        mock_folder_instance = MockFolderManager.instance.return_value
        mock_db_instance.dataChanged = pyqtSignal(str, int) # Ensure signal exists

        # --- Configure Mocks on the INSTANCE ---
        mock_folder_instance.get_all_root_folders.return_value = self.mock_root_folders
        captured_callbacks = {} # Store callbacks associated with a token

        def side_effect_unassigned(callback):
             print("DEBUG: side_effect_unassigned")
             token = self.tree_view._load_token # Capture token *at the time the mock is called*
             captured_callbacks[token] = callback
             self.callback_generator.generate_delayed_callback(
                 self.unassigned_recordings, 50, token
             )
        mock_folder_instance.get_recordings_not_in_folders.side_effect = side_effect_unassigned
        mock_folder_instance.get_recordings_in_folder.side_effect = lambda fid, cb: None # Dummy

        # Connect generator signal to trigger stored callbacks IF token matches
        def dispatch_if_valid(success, data, trigger_token):
             if not self.tree_view: return # Prevent errors during teardown
             if not data: return
             current_token = self.tree_view._load_token
             if trigger_token == current_token:
                  if trigger_token in captured_callbacks and captured_callbacks[trigger_token]:
                       print(f"DEBUG: Dispatching valid callback (token {trigger_token})")
                       captured_callbacks[trigger_token](success, data)
                  else: print(f"DEBUG: No valid callback found for token {trigger_token}")
             else: print(f"DEBUG: Ignoring stale callback (trigger {trigger_token}, current {current_token})")

        # Ensure connection is robust
        try:
            self.callback_generator.callback_triggered.disconnect()
        except TypeError: pass
        self.callback_generator.callback_triggered.connect(dispatch_if_valid)

        # --- Initialize TreeView INSIDE test method ---
        self.tree_view = UnifiedFolderTreeView(mock_db_instance)
        QApplication.processEvents()

        # --- First Load ---
        print("DEBUG: Triggering first load_structure")
        initial_token = self.tree_view._load_token
        self.tree_view.load_structure()
        first_load_token = self.tree_view._load_token
        self.assertEqual(first_load_token, initial_token + 1)
        self.wait_for_callbacks()
        print(f"DEBUG: Token after first load: {first_load_token}")

        # --- Second Load ---
        print("DEBUG: Triggering second load_structure")
        self.tree_view.load_structure()
        second_load_token = self.tree_view._load_token
        self.assertEqual(second_load_token, initial_token + 2)
        self.wait_for_callbacks()
        print(f"DEBUG: Token after second load: {second_load_token}")


        # --- Manually trigger the STALE callback from the FIRST load ---
        print(f"DEBUG: Manually triggering callback for STALE token {first_load_token}")
        self.callback_generator.generate_delayed_callback(self.unassigned_recordings, 1, first_load_token)
        self.wait_for_callbacks() # Wait for this manual trigger


        # --- Verification ---
        print("DEBUG: Verifying after stale callback...")
        recording_ids_in_model = {k[1] for k in self.tree_view.source_model.item_map if k[0] == "recording"}
        recording_ids_in_widget_map = set(self.tree_view.id_to_widget.keys())

        # Expect the state from the *second* (valid) load
        self.assertEqual(len(recording_ids_in_model), len(self.expected_ids), "Model count mismatch after stale callback ignored")
        self.assertEqual(len(recording_ids_in_widget_map), len(self.expected_ids), "Widget map count mismatch after stale callback ignored")
        self.assertSetEqual(recording_ids_in_model, self.expected_ids, "Model IDs mismatch after stale callback ignored")

        print("--- Finished test_token_invalidation ---")


if __name__ == '__main__':
    unittest.main()
