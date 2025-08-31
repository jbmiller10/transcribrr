"""Focused unit tests for app.db_utils using mocks (no real DB)."""

import unittest
from unittest.mock import Mock, patch
import sqlite3

from app import db_utils
from app.models.recording import Recording


class TestDbUtilsCRUD(unittest.TestCase):
    def setUp(self):
        self.conn = Mock()
        self.cursor = Mock()
        self.conn.cursor.return_value = self.cursor

    def test_create_recording_success(self):
        self.cursor.lastrowid = 7
        rec = ("file.wav", "/tmp/file.wav", "2024-01-02T03:04:05", "10:00")
        new_id = db_utils.create_recording(self.conn, rec)
        self.assertEqual(new_id, 7)
        self.conn.cursor.assert_called_once()
        self.cursor.execute.assert_called_once()
        self.conn.commit.assert_called_once()

    def test_create_recording_raises_on_duplicate_path(self):
        self.cursor.execute.side_effect = sqlite3.IntegrityError("duplicate")
        with self.assertRaises(db_utils.DuplicatePathError):
            db_utils.create_recording(self.conn, ("a", "/x", "t", "d"))

    def test_update_recording_ignores_invalid_fields(self):
        db_utils.update_recording(
            self.conn, 1, transcript="x", filename="name.wav", unknown="bad"
        )
        self.cursor.execute.assert_called_once()
        args = self.cursor.execute.call_args[0]
        self.assertIn("UPDATE", args[0])
        # unknown field should not appear in SQL
        self.assertNotIn("unknown", args[0])
        self.conn.commit.assert_called_once()

    def test_update_recording_no_fields(self):
        # Should be a no-op when no valid fields provided
        db_utils.update_recording(self.conn, 2)
        self.cursor.execute.assert_not_called()

    def test_delete_recording_executes(self):
        db_utils.delete_recording(self.conn, 5)
        self.cursor.execute.assert_called_once()
        self.conn.commit.assert_called_once()


class TestDbUtilsQueries(unittest.TestCase):
    def setUp(self):
        self.conn = Mock()
        self.cursor = Mock()
        self.conn.cursor.return_value = self.cursor

    def test_get_all_recordings(self):
        self.cursor.fetchall.return_value = [(1,), (2,)]
        rows = db_utils.get_all_recordings(self.conn)
        self.assertEqual(rows, [(1,), (2,)])
        self.cursor.execute.assert_called_once()

    def test_get_recording_by_id_none(self):
        self.cursor.fetchone.return_value = None
        rec = db_utils.get_recording_by_id(self.conn, 1)
        self.assertIsNone(rec)

    def test_get_recording_by_id_maps_fields(self):
        # Prepare a row matching schema order
        row = (
            3,
            "name.wav",
            "/p/name.wav",
            "pending",  # should be replaced with now() string
            "00:10",
            "raw",
            "proc",
            b"rf",
            b"pf",
            "orig",
        )
        self.cursor.fetchone.return_value = row
        result = db_utils.get_recording_by_id(self.conn, 3)
        self.assertIsInstance(result, Recording)
        self.assertEqual(result.id, 3)
        self.assertEqual(result.filename, "name.wav")
        self.assertEqual(result.file_path, "/p/name.wav")
        self.assertEqual(result.duration, "00:10")
        self.assertEqual(result.raw_transcript, "raw")
        self.assertEqual(result.processed_text, "proc")
        self.assertEqual(result.raw_transcript_formatted, b"rf")
        self.assertEqual(result.processed_text_formatted, b"pf")
        self.assertEqual(result.original_source_identifier, "orig")

    def test_recording_exists_true_false(self):
        self.cursor.fetchone.side_effect = [(1,), None]
        self.assertTrue(db_utils.recording_exists(self.conn, "/a"))
        self.assertFalse(db_utils.recording_exists(self.conn, "/b"))

    def test_search_recordings(self):
        self.cursor.fetchall.return_value = [(1, "a")] 
        rows = db_utils.search_recordings(self.conn, "term")
        self.assertEqual(rows, [(1, "a")])
        self.cursor.execute.assert_called_once()


class TestEnsureDatabaseExists(unittest.TestCase):
    @patch("app.db_utils.create_recordings_table")
    @patch("app.db_utils.create_folders_table")
    @patch("app.db_utils.create_recording_folders_table")
    @patch("app.db_utils.get_connection")
    @patch("app.db_utils.get_config_path")
    @patch("app.db_utils.create_config_file")
    def test_ensure_database_exists_creates_tables_and_config(
        self,
        mock_create_config,
        mock_get_config_path,
        mock_get_connection,
        mock_create_rf_table,
        mock_create_folders,
        mock_create_recordings,
    ):
        # Arrange: connection and config path
        mock_conn = Mock()
        mock_get_connection.return_value = mock_conn
        mock_get_config_path.return_value = "/tmp/nonexistent/config.json"

        # Act
        db_utils.ensure_database_exists()

        # Assert: tables created and config attempted
        mock_create_recordings.assert_called_once_with(mock_conn)
        mock_create_folders.assert_called_once_with(mock_conn)
        mock_create_rf_table.assert_called_once_with(mock_conn)
        mock_create_config.assert_called_once()
        mock_conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()

