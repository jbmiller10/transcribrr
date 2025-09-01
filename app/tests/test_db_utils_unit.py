"""Focused unit tests for app.db_utils using an in-memory SQLite database.

Reduces mocking to validate actual SQL behavior and state changes.
"""

import unittest
from unittest.mock import Mock, patch
import sqlite3

from app import db_utils
from app.models.recording import Recording


class TestDbUtilsCRUD(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        db_utils.create_recordings_table(self.conn)

    def test_create_recording_inserts_data_and_returns_id(self):
        rec = ("file.wav", "/tmp/file.wav", "2024-01-02T03:04:05", "10:00")
        new_id = db_utils.create_recording(self.conn, rec)
        # Verify actual database state
        cur = self.conn.cursor()
        cur.execute("SELECT id, filename, file_path, duration FROM recordings WHERE id=?", (new_id,))
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[1], "file.wav")
        self.assertEqual(row[2], "/tmp/file.wav")
        self.assertEqual(row[3], "10:00")
        self.assertGreater(new_id, 0)

    def test_create_recording_raises_on_duplicate_path(self):
        db_utils.create_recording(self.conn, ("a", "/x", "t", "d"))
        with self.assertRaises(db_utils.DuplicatePathError):
            db_utils.create_recording(self.conn, ("b", "/x", "t2", "d2"))

    def test_update_recording_ignores_invalid_fields(self):
        rid = db_utils.create_recording(self.conn, ("n.wav", "/p/n.wav", "t", "00:01"))
        # Update valid and invalid fields
        db_utils.update_recording(self.conn, rid, raw_transcript="x", filename="name.wav", unknown="bad")
        cur = self.conn.cursor()
        cur.execute("SELECT filename, raw_transcript FROM recordings WHERE id=?", (rid,))
        row = cur.fetchone()
        self.assertEqual(row[0], "name.wav")
        self.assertEqual(row[1], "x")

    def test_update_recording_no_fields(self):
        rid = db_utils.create_recording(self.conn, ("a.wav", "/p/a.wav", "t", "00:01"))
        # Should be a no-op when no valid fields provided
        db_utils.update_recording(self.conn, rid)
        cur = self.conn.cursor()
        cur.execute("SELECT filename FROM recordings WHERE id=?", (rid,))
        self.assertEqual(cur.fetchone()[0], "a.wav")

    def test_delete_recording_executes(self):
        rid = db_utils.create_recording(self.conn, ("b.wav", "/p/b.wav", "t", "00:02"))
        db_utils.delete_recording(self.conn, rid)
        cur = self.conn.cursor()
        cur.execute("SELECT 1 FROM recordings WHERE id=?", (rid,))
        self.assertIsNone(cur.fetchone())


class TestDbUtilsQueries(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        db_utils.create_recordings_table(self.conn)

    def test_get_all_recordings(self):
        # Insert two records
        db_utils.create_recording(self.conn, ("x.wav", "/p/x.wav", "t", "00:01"))
        db_utils.create_recording(self.conn, ("y.wav", "/p/y.wav", "t", "00:02"))
        rows = db_utils.get_all_recordings(self.conn)
        self.assertEqual(len(rows), 2)

    def test_get_recording_by_id_none(self):
        rec = db_utils.get_recording_by_id(self.conn, 999)
        self.assertIsNone(rec)

    def test_get_recording_by_id_maps_fields(self):
        rid = db_utils.create_recording(
            self.conn,
            ("name.wav", "/p/name.wav", "2024-01-02T03:04:05", "00:10", "raw", "proc"),
        )
        # Manually update blob fields and original_source_identifier
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE recordings SET raw_transcript_formatted=?, processed_text_formatted=?, original_source_identifier=? WHERE id=?",
            (b"rf", b"pf", "orig", rid),
        )
        self.conn.commit()
        result = db_utils.get_recording_by_id(self.conn, rid)
        self.assertIsInstance(result, Recording)
        self.assertEqual(result.id, rid)
        self.assertEqual(result.filename, "name.wav")
        self.assertEqual(result.file_path, "/p/name.wav")
        self.assertEqual(result.duration, "00:10")
        self.assertEqual(result.raw_transcript, "raw")
        self.assertEqual(result.processed_text, "proc")
        self.assertEqual(result.raw_transcript_formatted, b"rf")
        self.assertEqual(result.processed_text_formatted, b"pf")
        self.assertEqual(result.original_source_identifier, "orig")

    def test_recording_exists_true_false(self):
        db_utils.create_recording(self.conn, ("a.wav", "/a", "t", "00:01"))
        self.assertTrue(db_utils.recording_exists(self.conn, "/a"))
        self.assertFalse(db_utils.recording_exists(self.conn, "/b"))

    def test_search_recordings(self):
        db_utils.create_recording(self.conn, ("hello.wav", "/p/h.wav", "t", "00:01", "raw term", ""))
        rows = db_utils.search_recordings(self.conn, "term")
        self.assertGreaterEqual(len(rows), 1)


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
