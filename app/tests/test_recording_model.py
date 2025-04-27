# app/tests/test_recording_model.py
from app.RecordingFolderModel import RecordingFolderModel
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication
import os
import sys
import unittest

# Skip legacy tests in headless environment
raise unittest.SkipTest("Skipping legacy test in headless environment")
# Explicitly import QIcon and other necessary Qt classes here

# Add parent directory to path to import app modules
# Ensure this path adjustment is correct for your structure
if os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")) not in sys.path:
    sys.path.insert(
        0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    )


class TestRecordingFolderModel(unittest.TestCase):
    """Test cases for RecordingFolderModel."""

    @classmethod
    def setUpClass(cls):
        # Create QApplication instance if it doesn't exist
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        # Create the model
        self.model = RecordingFolderModel()

        # --- FIX: Create REAL QIcon objects here AFTER model init ---
        # This forces the use of the actual QIcon class for this test
        self.model.folder_icon = QIcon()
        self.model.folder_open_icon = QIcon()
        self.model.audio_icon = QIcon()
        self.model.video_icon = QIcon()
        self.model.file_icon = QIcon()
        # --- End FIX ---

        # Create some test recordings
        self.recordings = [
            # id, filename, file_path, date_created, duration, raw_transcript, processed_text, rt_formatted, pt_formatted
            [
                1,
                "Recording 1",
                "/path/1.mp3",
                "2023-10-01 10:00:00",
                "01:30",
                "transcript 1",
                "processed 1",
                None,
                None,
            ],
            [
                2,
                "Recording 2",
                "/path/2.mp3",
                "2023-10-02 10:00:00",
                "02:30",
                "transcript 2",
                "processed 2",
                None,
                None,
            ],
            [
                3,
                "Recording 3",
                "/path/3.mp3",
                "2023-10-03 10:00:00",
                "03:30",
                "transcript 3",
                "processed 3",
                None,
                None,
            ],
        ]

        # Create some test folders
        self.root_folder = {"type": "folder",
            "id": -1, "name": "Root", "children": []}
        self.folder1 = {"type": "folder", "id": 1,
            "name": "Folder 1", "children": []}
        self.folder2 = {"type": "folder", "id": 2,
            "name": "Folder 2", "children": []}

    def test_duplicate_prevention(self):
        """Test that duplicates are prevented via model single source of truth."""
        # Add the root folder
        root_item = self.model.add_folder_item(self.root_folder)

        # Add a recording
        rec = self.recordings[0]
        self.model.add_recording_item(rec, root_item)

        # Verify it's in the model
        self.assertIn(("recording", rec[0]), self.model.item_map)

        # Try to add it again
        self.model.add_recording_item(rec, root_item)

        # Verify no duplicates (should still be only one entry)
        recording_ids = set()
        for item_key in self.model.item_map.keys():
            if item_key[0] == "recording":
                recording_ids.add(item_key[1])

        self.assertEqual(
            len(recording_ids),
            1,
            "There should only be one recording in the model, not duplicates",
        )

        # Try adding to a different folder (which shouldn't be allowed)
        folder1_item = self.model.add_folder_item(self.folder1, root_item)
        self.model.add_recording_item(rec, folder1_item)

        # Still should have only one recording in the model
        recording_ids.clear()
        for item_key in self.model.item_map.keys():
            if item_key[0] == "recording":
                recording_ids.add(item_key[1])

        self.assertEqual(
            len(recording_ids),
            1,
            "After adding to another folder, there should still only be one recording",
        )

    def test_get_item_by_id(self):
        """Test getting items by ID."""
        # Add folders and recordings
        root_item = self.model.add_folder_item(self.root_folder)
        folder1_item = self.model.add_folder_item(self.folder1, root_item)

        for rec in self.recordings:
            self.model.add_recording_item(rec, folder1_item)

        # Test getting recordings
        for rec in self.recordings:
            item = self.model.get_item_by_id(rec[0], "recording")
            self.assertIsNotNone(
                item, f"Should find recording with ID {rec[0]}")
            self.assertEqual(
                item.data(RecordingFolderModel.ITEM_ID_ROLE), rec[0])
            self.assertEqual(
                item.data(RecordingFolderModel.ITEM_TYPE_ROLE), "recording"
            )

        # Test getting folders
        folder_item = self.model.get_item_by_id(self.folder1["id"], "folder")
        self.assertIsNotNone(
            folder_item, f"Should find folder with ID {self.folder1['id']}"
        )
        self.assertEqual(
            folder_item.data(
                RecordingFolderModel.ITEM_ID_ROLE), self.folder1["id"]
        )
        self.assertEqual(
            folder_item.data(RecordingFolderModel.ITEM_TYPE_ROLE), "folder"
        )

        # Test nonexistent items
        self.assertIsNone(
            self.model.get_item_by_id(999, "recording"),
            "Should return None for nonexistent recording",
        )
        self.assertIsNone(
            self.model.get_item_by_id(999, "folder"),
            "Should return None for nonexistent folder",
        )

    def test_clear_model(self):
        """Test clearing the model."""
        # Add folders and recordings
        root_item = self.model.add_folder_item(self.root_folder)
        folder1_item = self.model.add_folder_item(self.folder1, root_item)

        for rec in self.recordings:
            self.model.add_recording_item(rec, folder1_item)

        # Verify items exist
        self.assertGreater(len(self.model.item_map), 0,
                           "Model should have items")

        # Clear the model
        self.model.clear_model()

        # Verify items were cleared
        self.assertEqual(
            len(self.model.item_map), 0, "Model map should be empty after clear"
        )
        self.assertEqual(
            self.model.rowCount(), 0, "Model should have no rows after clear"
        )


if __name__ == "__main__":
    unittest.main()
