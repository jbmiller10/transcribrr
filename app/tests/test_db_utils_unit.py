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

    def test_create_recording_with_empty_tuple_raises(self):
        with self.assertRaises(ValueError):
            db_utils.create_recording(self.conn, tuple())

    def test_create_recording_sql_injection_literal(self):
        malicious = "'; DROP TABLE recordings; --"
        rec = (malicious, "/tmp/mal.wav", "2024-01-02T03:04:05", "10:00")
        new_id = db_utils.create_recording(self.conn, rec)
        cur = self.conn.cursor()
        cur.execute("SELECT filename FROM recordings WHERE id=?", (new_id,))
        self.assertEqual(cur.fetchone()[0], malicious)

    def test_create_recording_large_fields(self):
        # Keep size reasonable for unit tests while still non-trivial
        big_text = "x" * 1024 * 1024  # 1MB
        rec = ("big.wav", "/tmp/big.wav", "2024-01-02T03:04:05", "10:00", big_text, big_text)
        new_id = db_utils.create_recording(self.conn, rec)
        self.assertGreater(new_id, 0)

    def test_create_recording_null_in_required_field_raises(self):
        with self.assertRaises(sqlite3.IntegrityError):
            db_utils.create_recording(self.conn, ("f.wav", None, "2024-01-01", "10:00"))

    def test_update_recording_injection_in_value_is_literal(self):
        rid = db_utils.create_recording(self.conn, ("u.wav", "/p/u.wav", "t", "00:01"))
        payload = "'; DROP TABLE recordings; --"
        db_utils.update_recording(self.conn, rid, raw_transcript=payload)
        cur = self.conn.cursor()
        cur.execute("SELECT raw_transcript FROM recordings WHERE id=?", (rid,))
        self.assertEqual(cur.fetchone()[0], payload)

    def test_update_nonexistent_id_succeeds_silently(self):
        # No rows affected but should not raise
        db_utils.update_recording(self.conn, 9999, filename="none.wav")

    def test_delete_nonexistent_id_succeeds(self):
        # Deleting a non-existent row should not raise
        db_utils.delete_recording(self.conn, 9999)


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

    def test_get_recording_by_id_negative_returns_none(self):
        self.assertIsNone(db_utils.get_recording_by_id(self.conn, -1))

    def test_get_recording_by_id_pending_date_is_replaced(self):
        # Insert a row with 'pending' date to simulate corrupted/placeholder value
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO recordings(filename, file_path, date_created, duration) VALUES(?,?,?,?)",
            ("p.wav", "/p/p.wav", "pending", "00:01"),
        )
        rid = cur.lastrowid
        self.conn.commit()
        rec = db_utils.get_recording_by_id(self.conn, rid)
        self.assertIsNotNone(rec)
        self.assertNotEqual(rec.date_created, "pending")
        # Ensure it is ISO formatted
        from datetime import datetime
        datetime.fromisoformat(rec.date_created)

    def test_get_recording_by_id_missing_legacy_column_handled(self):
        # Simulate legacy schema by mocking fetchone to return 9 columns
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (
            1, "f.wav", "/p", "2024-01-01", "10:00", None, None, None, None
        )
        rec = db_utils.get_recording_by_id(mock_conn, 1)
        self.assertIsInstance(rec, Recording)
        self.assertIsNone(rec.original_source_identifier)

    def test_get_recording_by_id_sql_injection_in_id_is_literal(self):
        # Passing a malicious string should not cause injection; it should just return None
        db_utils.create_recording(self.conn, ("a.wav", "/p/a.wav", "t", "00:01"))
        result = db_utils.get_recording_by_id(
            self.conn, "1 OR 1=1; DROP TABLE recordings; --"  # type: ignore[arg-type]
        )
        self.assertIsNone(result)

    def test_recording_exists_with_special_chars(self):
        path = "/path/with'quotes\"and%wildcards_"
        db_utils.create_recording(self.conn, ("s.wav", path, "t", "00:01"))
        self.assertTrue(db_utils.recording_exists(self.conn, path))

    def test_search_empty_string_returns_all(self):
        # Insert a few records
        for i in range(3):
            db_utils.create_recording(self.conn, (f"f{i}.wav", f"/p/f{i}.wav", "t", "00:01"))
        rows = db_utils.search_recordings(self.conn, "")
        self.assertEqual(len(rows), 3)

    def test_search_unicode_term(self):
        db_utils.create_recording(self.conn, ("🎵 録音(レコーディング).wav", "/path/音楽", "2024-01-01", "10:00"))
        rows = db_utils.search_recordings(self.conn, "録音")
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

    def test_ensure_database_exists_config_creation_failure_propagates(self):
        mock_conn = Mock()
        with patch("app.db_utils.get_connection", return_value=mock_conn), \
             patch("app.db_utils.create_recordings_table"), \
             patch("app.db_utils.create_folders_table"), \
             patch("app.db_utils.create_recording_folders_table"), \
             patch("app.db_utils.os.path.exists", return_value=False), \
             patch("app.db_utils.create_config_file", side_effect=PermissionError("Cannot write")):
            with self.assertRaises(PermissionError):
                db_utils.ensure_database_exists()
            mock_conn.close.assert_called_once()


class TestConnectionAndErrors(unittest.TestCase):
    def test_get_connection_locked_raises_runtimeerror_and_logs(self):
        with patch("app.db_utils.sqlite3.connect", side_effect=sqlite3.OperationalError("database is locked")), \
             patch("app.db_utils.get_database_path", return_value="/x/db.sqlite"), \
             patch("app.db_utils.os.path.dirname", return_value="/x"), \
             patch("app.db_utils.os.makedirs") as mk, \
             patch("app.db_utils.logger") as log:
            with self.assertRaises(RuntimeError):
                db_utils.get_connection()
            mk.assert_called_once()
            log.critical.assert_called()

    def test_get_connection_corrupted_raises_runtimeerror(self):
        with patch("app.db_utils.sqlite3.connect", side_effect=sqlite3.DatabaseError("file is not a database")):
            with self.assertRaises(RuntimeError):
                db_utils.get_connection()

    def test_get_connection_permission_denied_propagates(self):
        with patch("app.db_utils.os.makedirs", side_effect=PermissionError("denied")), \
             patch("app.db_utils.sqlite3.connect") as conn:
            with self.assertRaises(PermissionError):
                db_utils.get_connection()
            conn.assert_not_called()

    def test_create_recording_not_null_violation_propagates(self):
        # Use mock connection whose cursor.execute raises non-unique IntegrityError
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = sqlite3.IntegrityError("NOT NULL constraint failed: recordings.filename")
        with self.assertRaises(sqlite3.IntegrityError):
            db_utils.create_recording(mock_conn, (None, "/p/x", "t", "d"))

    def test_delete_recording_integrity_error_propagates(self):
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = sqlite3.IntegrityError("FOREIGN KEY constraint failed")
        with self.assertRaises(sqlite3.IntegrityError):
            db_utils.delete_recording(mock_conn, 1)

    def test_recording_exists_database_error_propagates(self):
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = sqlite3.DatabaseError("malformed")
        with self.assertRaises(sqlite3.DatabaseError):
            db_utils.recording_exists(mock_conn, "/any")

    def test_get_connection_success_sets_pragmas(self):
        mock_conn = Mock()
        with patch("app.db_utils.sqlite3.connect", return_value=mock_conn) as pconnect, \
             patch("app.db_utils.get_database_path", return_value="/x/db.sqlite"), \
             patch("app.db_utils.os.path.dirname", return_value="/x"), \
             patch("app.db_utils.os.makedirs"):
            conn = db_utils.get_connection()
            self.assertIs(conn, mock_conn)
            mock_conn.execute.assert_called_with("PRAGMA foreign_keys = ON")
            pconnect.assert_called_with(
                "/x/db.sqlite", timeout=30.0, isolation_level=None, check_same_thread=False
            )

    def test_create_recordings_table_success_commits_and_indexes(self):
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        db_utils.create_recordings_table(mock_conn)
        self.assertGreaterEqual(mock_cursor.execute.call_count, 2)
        mock_conn.commit.assert_called_once()

    def test_create_recordings_table_sql_error_logs_and_raises(self):
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = sqlite3.OperationalError("near \"TABL\": syntax error")
        with patch("app.db_utils.logger") as log:
            with self.assertRaises(sqlite3.OperationalError):
                db_utils.create_recordings_table(mock_conn)
            log.error.assert_called()

    def test_update_recording_locked_raises(self):
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = sqlite3.OperationalError("database is locked")
        with self.assertRaises(sqlite3.OperationalError):
            db_utils.update_recording(mock_conn, 1, filename="x")


    def test_create_config_file_dump_error_propagates(self):
        with patch("app.db_utils.get_config_path", return_value="/tmp/config.json"), \
             patch("builtins.open") as mock_open, \
             patch("app.db_utils.json.dump", side_effect=OSError("No space left on device")):
            mock_open.return_value.__enter__.return_value = Mock()
            with self.assertRaises(OSError):
                db_utils.create_config_file()

    def test_get_connection_disk_io_error_raises_runtimeerror(self):
        with patch("app.db_utils.sqlite3.connect", side_effect=sqlite3.OperationalError("disk I/O error")):
            with self.assertRaises(RuntimeError):
                db_utils.get_connection()

    def test_ensure_database_exists_connection_failure_short_circuits(self):
        with patch("app.db_utils.get_connection", side_effect=RuntimeError("connect fail")), \
             patch("app.db_utils.create_recordings_table") as cr, \
             patch("app.db_utils.create_folders_table") as cf, \
             patch("app.db_utils.create_recording_folders_table") as crf:
            with self.assertRaises(RuntimeError):
                db_utils.ensure_database_exists()
            cr.assert_not_called()
            cf.assert_not_called()
            crf.assert_not_called()


if __name__ == "__main__":
    unittest.main()
