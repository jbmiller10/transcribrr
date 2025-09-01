"""
Atomic rename tests against the real RecentRecordingsWidget.handle_recording_rename.

Uses real filesystem operations in a temporary directory and minimal mocking
for database and UI boundaries.
"""

from unittest.mock import patch
import shutil
import tempfile
import os
import unittest

from app.RecentRecordingsWidget import RecentRecordingsWidget as RRW


class DummySignal:
    def connect(self, _):
        # No-op signal connector for tests
        return None


class DummyDBManager:
    def __init__(self, should_raise=False):
        self.should_raise = should_raise
        self.calls = []
        self.error_occurred = DummySignal()

    def update_recording(self, recording_id, on_success_cb, **kwargs):
        # Record the call for assertions
        self.calls.append((recording_id, kwargs))
        if self.should_raise:
            raise RuntimeError("DB update failed")
        # Emulate successful async completion by calling the callback
        on_success_cb()


class DummyNameEditable:
    def __init__(self, initial_text=""):
        self.last_set = None
        self._text = initial_text

    def setText(self, text):
        self.last_set = text
        self._text = text

    def text(self):
        return self._text


class DummyRecordingWidget:
    def __init__(self, file_path):
        self.file_path = file_path
        base, ext = os.path.splitext(os.path.basename(file_path))
        self.filename_no_ext = base
        self._ext = ext
        self._filename = base + ext
        self.name_editable = DummyNameEditable(base)
        self.updated = []

    def get_filename(self):
        return self._filename

    def update_data(self, data):
        # Mirror minimal behavior used by widget code
        if "filename" in data:
            self.filename_no_ext = data["filename"]
            self._filename = data["filename"] + self._ext
        if "file_path" in data:
            self.file_path = data["file_path"]
        self.updated.append(data)


def make_widget_instance(db_manager, recording_widget_map):
    # Create instance without running __init__ (avoids heavy Qt setup)
    inst = RRW.__new__(RRW)
    inst.db_manager = db_manager
    inst.unified_view = type("DummyView", (), {"id_to_widget": recording_widget_map})()
    # Stub out UI helpers used by handler
    inst.show_status_message = lambda *_: None
    return inst


class TestAtomicRenameSuccess(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.src = os.path.join(self.temp_dir, "test_recording.mp3")
        with open(self.src, "w", encoding="utf-8") as f:
            f.write("content")

        self.db = DummyDBManager()
        self.item = DummyRecordingWidget(self.src)
        self.widget = make_widget_instance(self.db, {1: self.item})

        # Patch error/info dialogs so tests don't try to render UI
        patcher = patch("app.RecentRecordingsWidget.show_error_message")
        self.addCleanup(patcher.stop)
        self.mock_show_error = patcher.start()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_simple_rename_success(self):
        self.widget.handle_recording_rename(1, "renamed_recording")

        new_path = os.path.join(self.temp_dir, "renamed_recording.mp3")
        self.assertFalse(os.path.exists(self.src), "Old file should be gone")
        self.assertTrue(os.path.exists(new_path), "New file should exist")

        # Database call should include both filename and file_path
        self.assertEqual(len(self.db.calls), 1)
        rec_id, kwargs = self.db.calls[0]
        self.assertEqual(rec_id, 1)
        self.assertEqual(kwargs.get("filename"), "renamed_recording.mp3")
        self.assertEqual(kwargs.get("file_path"), new_path)

        # Widget internal state updated
        self.assertEqual(self.item.file_path, new_path)
        self.assertEqual(self.item.filename_no_ext, "renamed_recording")

    def test_rename_preserves_extension(self):
        self.widget.handle_recording_rename(1, "name_only_no_ext")
        self.assertTrue(
            os.path.exists(os.path.join(self.temp_dir, "name_only_no_ext.mp3"))
        )

    def test_rename_with_special_characters(self):
        new_base = "weird name_ä漢字🙂"
        self.widget.handle_recording_rename(1, new_base)
        self.assertTrue(
            os.path.exists(os.path.join(self.temp_dir, f"{new_base}.mp3"))
        )


class TestAtomicRenameFilesystemErrors(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        # Do not create self.src to simulate missing file in first test
        self.db = DummyDBManager()
        self.item = DummyRecordingWidget(os.path.join(self.temp_dir, "missing.mp3"))
        self.widget = make_widget_instance(self.db, {1: self.item})

        patcher = patch("app.RecentRecordingsWidget.show_error_message")
        self.addCleanup(patcher.stop)
        self.mock_show_error = patcher.start()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_source_file_not_found(self):
        self.widget.handle_recording_rename(1, "any")
        # Should show error and do nothing else
        self.assertFalse(self.db.calls, "DB should not be called when missing source")
        self.mock_show_error.assert_called()

    def test_destination_already_exists(self):
        # Create real source and an existing destination
        src = os.path.join(self.temp_dir, "a.mp3")
        with open(src, "w", encoding="utf-8"):
            pass
        existing = os.path.join(self.temp_dir, "b.mp3")
        with open(existing, "w", encoding="utf-8"):
            pass

        # Update the item to point to real source
        self.item.file_path = src
        self.item.filename_no_ext = "a"
        self.item.name_editable = DummyNameEditable("b")

        # Swap in a fresh widget referencing the updated item
        self.widget = make_widget_instance(self.db, {1: self.item})

        self.widget.handle_recording_rename(1, "b")

        # Should not have moved the file
        self.assertTrue(os.path.exists(src))
        self.assertTrue(os.path.exists(existing))
        self.assertFalse(self.db.calls, "DB should not be called when target exists")
        self.assertEqual(self.item.name_editable.last_set, "a")


class TestAtomicRenameDatabaseErrors(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.src = os.path.join(self.temp_dir, "x.mp3")
        with open(self.src, "w", encoding="utf-8"):
            pass

        self.db = DummyDBManager(should_raise=True)
        self.item = DummyRecordingWidget(self.src)
        self.widget = make_widget_instance(self.db, {1: self.item})

        patcher = patch("app.RecentRecordingsWidget.show_error_message")
        self.addCleanup(patcher.stop)
        self.mock_show_error = patcher.start()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_database_update_fails_rollback_succeeds(self):
        # Normal os.rename for forward and rollback
        self.widget.handle_recording_rename(1, "y")

        # Should have rolled back => original remains, destination does not
        dest = os.path.join(self.temp_dir, "y.mp3")
        self.assertTrue(os.path.exists(self.src))
        self.assertFalse(os.path.exists(dest))
        # Error dialog shown
        self.mock_show_error.assert_called()

    def test_database_update_fails_rollback_fails(self):
        dest = os.path.join(self.temp_dir, "y.mp3")

        rename_calls = {"count": 0}
        real_rename = os.rename

        def flaky_rename(a, b):
            rename_calls["count"] += 1
            if rename_calls["count"] == 1:
                return real_rename(a, b)  # forward rename succeeds
            raise OSError("rollback failed")

        with patch("os.rename", side_effect=flaky_rename):
            self.widget.handle_recording_rename(1, "y")

        # Forward rename happened, rollback failed => dest exists, src gone
        self.assertFalse(os.path.exists(self.src))
        self.assertTrue(os.path.exists(dest))
        self.mock_show_error.assert_called()


if __name__ == "__main__":
    unittest.main()
