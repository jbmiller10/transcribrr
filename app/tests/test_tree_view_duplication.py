# app/tests/test_tree_view_duplication.py
import sys
import unittest
from unittest.mock import MagicMock, patch, call
import os
import time
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, Qt
from PyQt6.QtWidgets import QApplication

# Add parent directory to path to import app modules
# Ensure this path adjustment is correct for your structure
if os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")) not in sys.path:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.UnifiedFolderTreeView import UnifiedFolderTreeView
# We will mock DatabaseManager and FolderManager where they are used

# Mock class for generating delayed callbacks
class DelayedCallbackGenerator(QObject):
    callback_triggered = pyqtSignal(bool, list, int) # Add token to signal

    def __init__(self):
        super().__init__()
        self.pending_callbacks = 0 # Use a simple counter

    def generate_delayed_callback(self, data, delay_ms, token):
        self.pending_callbacks += 1
        QTimer.singleShot(delay_ms, lambda: self._emit_callback(data, token))

    def _emit_callback(self, data, token):
        if self: # Check if instance still exists
            self.callback_triggered.emit(True, data, token)
            self.pending_callbacks -= 1

    def is_finished(self):
        return self.pending_callbacks <= 0


class TestTreeViewDuplication(unittest.TestCase):
    """Test cases for tree view duplication prevention."""

    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        # Mock DatabaseManager used by UnifiedFolderTreeView
        # Patch it where it's imported/used by the class under test
        self.db_manager_patcher = patch('app.UnifiedFolderTreeView.DatabaseManager', autospec=True)
        self.MockDatabaseManager = self.db_manager_patcher.start()
        self.mock_db_instance = self.MockDatabaseManager.return_value
        self.mock_db_instance.dataChanged = pyqtSignal(str, int) # Add the required signal


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


    def tearDown(self):
        # Stop patchers started in setUp
        self.db_manager_patcher.stop()

        # Clean up tree_view if created
        if hasattr(self, 'tree_view'):
             self.tree_view.deleteLater()
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
    # Use patch context managers here for isolation
    @patch('app.FolderManager.FolderManager.get_recordings_not_in_folders', autospec=True)
    @patch('app.FolderManager.FolderManager.get_recordings_in_folder', autospec=True)
    @patch('app.FolderManager.FolderManager.get_all_root_folders', autospec=True)
    def test_model_refresh_without_duplicates(self, mock_get_roots, mock_get_in_folder, mock_get_not_in):
        """Test that refreshing the model doesn't create duplicates."""
        print("\n--- Starting test_model_refresh_without_duplicates ---")

        # --- Configure Mocks ---
        mock_get_roots.return_value = self.mock_root_folders

        callback_map = {} # Store callbacks to be triggered

        def side_effect_unassigned(callback):
            print("DEBUG: side_effect_unassigned called")
            callback_map['unassigned'] = callback # Store the actual callback
            # Schedule trigger via generator
            self.callback_generator.generate_delayed_callback(
                self.unassigned_recordings, 50, self.tree_view._load_token # Pass current token
            )
        mock_get_not_in.side_effect = side_effect_unassigned

        def side_effect_folders(folder_id, callback):
            print(f"DEBUG: side_effect_folders called for ID {folder_id}")
            if folder_id == 1:
                callback_map['folder1'] = callback
                self.callback_generator.generate_delayed_callback(
                    self.folder1_recordings, 100, self.tree_view._load_token
                )
            elif folder_id == 2:
                callback_map['folder2'] = callback
                self.callback_generator.generate_delayed_callback(
                    self.folder2_recordings, 75, self.tree_view._load_token
                )
        mock_get_in_folder.side_effect = side_effect_folders

        # Connect generator signal to trigger stored callbacks IF token matches
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
        # TreeView instance is created *within* the patched context
        self.tree_view = UnifiedFolderTreeView(self.mock_db_instance)
        QApplication.processEvents() # Allow init signals if any

        # --- First Load ---
        print("DEBUG: Triggering first load_structure")
        initial_token = self.tree_view._load_token
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
        self.tree_view.load_structure() # Should trigger cleanup and new load
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
    @patch('app.FolderManager.FolderManager.get_recordings_not_in_folders', autospec=True)
    @patch('app.FolderManager.FolderManager.get_recordings_in_folder', autospec=True)
    @patch('app.FolderManager.FolderManager.get_all_root_folders', autospec=True)
    def test_token_invalidation(self, mock_get_roots, mock_get_in_folder, mock_get_not_in):
        """Test that load tokens properly invalidate stale callbacks."""
        print("\n--- Starting test_token_invalidation ---")

        # --- Configure Mocks ---
        mock_get_roots.return_value = self.mock_root_folders
        captured_callbacks = {} # Store callbacks

        def side_effect_unassigned(callback):
             print("DEBUG: side_effect_unassigned")
             # Store callback associated with the current load token
             captured_callbacks[self.tree_view._load_token] = callback
             # Schedule trigger via generator, passing the token it was created with
             self.callback_generator.generate_delayed_callback(
                 self.unassigned_recordings, 50, self.tree_view._load_token
             )
        mock_get_not_in.side_effect = side_effect_unassigned

        # Don't need folder mocks for this specific test, but set a dummy side effect
        mock_get_in_folder.side_effect = lambda folder_id, callback: None

        # Connect generator signal to trigger stored callbacks IF token matches
        def dispatch_if_valid(success, data, trigger_token):
             current_token = self.tree_view._load_token
             if trigger_token == current_token: # Check token validity
                  if trigger_token in captured_callbacks and captured_callbacks[trigger_token]:
                       print(f"DEBUG: Dispatching valid callback (token {trigger_token})")
                       captured_callbacks[trigger_token](success, data)
                  else:
                      print(f"DEBUG: No valid callback found for token {trigger_token}")
             else:
                  print(f"DEBUG: Ignoring stale callback (trigger {trigger_token}, current {current_token})")

        self.callback_generator.callback_triggered.connect(dispatch_if_valid)

        # --- Initialize TreeView ---
        self.tree_view = UnifiedFolderTreeView(self.mock_db_instance)
        QApplication.processEvents()

        # --- First Load ---
        print("DEBUG: Triggering first load_structure")
        initial_token = self.tree_view._load_token
        self.tree_view.load_structure()
        first_load_token = self.tree_view._load_token # Token used for the first load
        self.assertEqual(first_load_token, initial_token + 1, "Token check after first load")
        self.wait_for_callbacks() # Wait for first load callback generation
        self.assertTrue(self.callback_generator.is_finished(), "Callbacks should be finished after first wait")
        print(f"DEBUG: Token after first load: {first_load_token}")

        # --- Second Load ---
        print("DEBUG: Triggering second load_structure")
        self.tree_view.load_structure()
        second_load_token = self.tree_view._load_token # Token for the second load
        self.assertEqual(second_load_token, initial_token + 2, "Token check after second load")
        self.wait_for_callbacks() # Wait for second load callback generation
        self.assertTrue(self.callback_generator.is_finished(), "Callbacks should be finished after second wait")
        print(f"DEBUG: Token after second load: {second_load_token}")


        # --- Manually trigger the STALE callback from the FIRST load ---
        print(f"DEBUG: Manually triggering callback for STALE token {first_load_token}")
        # Use the generator to emit the signal, simulating the delayed callback
        # We pass the *stale* token (first_load_token)
        self.callback_generator.generate_delayed_callback(self.unassigned_recordings, 1, first_load_token)
        self.wait_for_callbacks() # Wait for this manual trigger


        # --- Verification ---
        # The dispatch_if_valid function should have ignored the stale callback
        print("DEBUG: Verifying after stale callback...")
        recording_ids_in_model = {k[1] for k in self.tree_view.source_model.item_map if k[0] == "recording"}
        recording_ids_in_widget_map = set(self.tree_view.id_to_widget.keys())

        # Since the second load also generated callbacks which *should* have run successfully,
        # we expect the final state to contain all recordings from the second load.
        self.assertEqual(len(recording_ids_in_model), len(self.expected_ids),
                         f"Model count mismatch after stale callback ignored. Expected {len(self.expected_ids)}, Got {len(recording_ids_in_model)}")
        self.assertEqual(len(recording_ids_in_widget_map), len(self.expected_ids),
                         f"Widget map count mismatch after stale callback ignored. Expected {len(self.expected_ids)}, Got {len(recording_ids_in_widget_map)}")
        self.assertSetEqual(recording_ids_in_model, self.expected_ids, "Model IDs mismatch after stale callback ignored")

        print("--- Finished test_token_invalidation ---")


if __name__ == '__main__':
    unittest.main()
