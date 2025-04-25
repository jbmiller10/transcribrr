# app/tests/test_tree_view_duplication.py
import sys
import unittest
from unittest.mock import MagicMock, patch, call # Keep call if needed elsewhere
import os
import time
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, Qt
from PyQt6.QtWidgets import QApplication

# Add parent directory to path if needed
if os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")) not in sys.path:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.UnifiedFolderTreeView import UnifiedFolderTreeView
# We still import FolderManager to patch its methods later
from app.FolderManager import FolderManager
# No need to import DatabaseManager here, we patch it via string

# ... (DelayedCallbackGenerator class remains the same) ...

class TestTreeViewDuplication(unittest.TestCase):
    """Test cases for tree view duplication prevention."""

    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        # --- FIX: Correct patch target for DatabaseManager ---
        # Patch DatabaseManager where it's DEFINED, not where it's imported in the test target.
        # Assuming it's defined in 'app.DatabaseManager'
        self.db_manager_patcher = patch('app.DatabaseManager.DatabaseManager', autospec=True)
        # --- End FIX ---

        # Start the patcher and get the mock class and instance
        self.MockDatabaseManager = self.db_manager_patcher.start()
        self.mock_db_instance = self.MockDatabaseManager.return_value
        # Ensure the mock instance has the necessary signal attribute
        self.mock_db_instance.dataChanged = pyqtSignal(str, int)


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

        # Patch FolderManager methods using context managers within test methods
        # We still need to patch the singleton instance if FolderManager uses .instance()
        self.folder_manager_patcher = patch('app.FolderManager.FolderManager', autospec=True)
        self.MockFolderManager = self.folder_manager_patcher.start()
        self.mock_folder_instance = self.MockFolderManager.instance.return_value # Mock the instance returned by the singleton accessor


    def tearDown(self):
        # Stop patchers started in setUp
        self.db_manager_patcher.stop()
        self.folder_manager_patcher.stop()

        # Clean up tree_view if created
        if hasattr(self, 'tree_view'):
             self.tree_view.deleteLater()
        QApplication.processEvents() # Ensure cleanup

    # ... (wait_for_callbacks helper remains the same) ...

    # --- Test Method for Refresh Logic ---
    # Patch the INSTANCE methods now using the mock_folder_instance from setUp
    def test_model_refresh_without_duplicates(self):
        """Test that refreshing the model doesn't create duplicates."""
        print("\n--- Starting test_model_refresh_without_duplicates ---")

        # --- Configure Mocks on the INSTANCE ---
        self.mock_folder_instance.get_all_root_folders.return_value = self.mock_root_folders

        callback_map = {} # Store callbacks to be triggered

        def side_effect_unassigned(callback):
            print("DEBUG: side_effect_unassigned called")
            callback_map['unassigned'] = callback # Store the actual callback
            self.callback_generator.generate_delayed_callback(
                self.unassigned_recordings, 50, self.tree_view._load_token
            )
        self.mock_folder_instance.get_recordings_not_in_folders.side_effect = side_effect_unassigned

        def side_effect_folders(folder_id, callback):
            print(f"DEBUG: side_effect_folders called for ID {folder_id}")
            key = f'folder{folder_id}'
            callback_map[key] = callback
            data = self.folder1_recordings if folder_id == 1 else self.folder2_recordings
            delay = 100 if folder_id == 1 else 75
            self.callback_generator.generate_delayed_callback(
                data, delay, self.tree_view._load_token
            )
        self.mock_folder_instance.get_recordings_in_folder.side_effect = side_effect_folders

        # Connect generator signal to trigger stored callbacks IF token matches
        # (dispatch_if_valid remains the same as previous version)
        def dispatch_if_valid(success, data, trigger_token):
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

        self.callback_generator.callback_triggered.connect(dispatch_if_valid)

        # --- Initialize TreeView ---
        # It will now use the MOCKED DatabaseManager instance implicitly
        self.tree_view = UnifiedFolderTreeView(self.mock_db_instance)
        QApplication.processEvents()

        # --- First Load ---
        print("DEBUG: Triggering first load_structure")
        self.tree_view.load_structure()
        self.wait_for_callbacks()

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
        self.mock_folder_instance.get_recordings_not_in_folders.reset_mock()
        self.mock_folder_instance.get_recordings_in_folder.reset_mock()
        callback_map.clear() # Clear old callbacks before triggering new ones

        self.tree_view.load_structure()
        self.wait_for_callbacks()

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
    # Patch the INSTANCE methods using the mock_folder_instance from setUp
    def test_token_invalidation(self):
        """Test that load tokens properly invalidate stale callbacks."""
        print("\n--- Starting test_token_invalidation ---")

        # --- Configure Mocks on the INSTANCE ---
        self.mock_folder_instance.get_all_root_folders.return_value = self.mock_root_folders
        captured_callbacks = {} # Store callbacks associated with a token

        def side_effect_unassigned(callback):
             print("DEBUG: side_effect_unassigned")
             token = self.tree_view._load_token # Capture token *at the time the mock is called*
             captured_callbacks[token] = callback
             self.callback_generator.generate_delayed_callback(
                 self.unassigned_recordings, 50, token
             )
        self.mock_folder_instance.get_recordings_not_in_folders.side_effect = side_effect_unassigned
        self.mock_folder_instance.get_recordings_in_folder.side_effect = lambda fid, cb: None # Dummy

        # Connect generator signal to trigger stored callbacks IF token matches
        def dispatch_if_valid(success, data, trigger_token):
             current_token = self.tree_view._load_token
             if trigger_token == current_token:
                  if trigger_token in captured_callbacks and captured_callbacks[trigger_token]:
                       print(f"DEBUG: Dispatching valid callback (token {trigger_token})")
                       captured_callbacks[trigger_token](success, data)
                  else: print(f"DEBUG: No valid callback found for token {trigger_token}")
             else: print(f"DEBUG: Ignoring stale callback (trigger {trigger_token}, current {current_token})")

        self.callback_generator.callback_triggered.connect(dispatch_if_valid)

        # --- Initialize TreeView ---
        self.tree_view = UnifiedFolderTreeView(self.mock_db_instance)
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
